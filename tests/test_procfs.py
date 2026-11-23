"""/proc ayrıştırıcıları ve salt-okunur okuyucu testleri (sahte /proc ağacıyla)."""
import builtins

import pytest

from conftest import DISKSTATS, MEMINFO, STAT, VMSTAT
from pardusinsight.collectors import procfs
from pardusinsight.collectors.procfs import (ProcFsReader, is_physical_disk, meminfo_to_memory,
                                             parse_diskstats, parse_meminfo, parse_pressure,
                                             parse_stat, parse_vmstat)


def test_parse_meminfo_converts_kb_to_bytes():
    values = parse_meminfo(MEMINFO)
    assert values["MemTotal"] == 8_000_000 * 1024
    assert values["MemAvailable"] == 2_000_000 * 1024
    assert values["HugePages_Total"] == 0  # birimsiz alan olduğu gibi kalır
    mem = meminfo_to_memory(values)
    assert mem.total == 8_000_000 * 1024
    assert mem.swap_total - mem.swap_free == 500_000 * 1024
    assert mem.available_estimated is False


def test_meminfo_without_memavailable_is_estimated():
    text = "MemTotal: 1000 kB\nMemFree: 100 kB\nBuffers: 50 kB\nCached: 200 kB\n"
    mem = meminfo_to_memory(parse_meminfo(text))
    assert mem.available == 350 * 1024
    assert mem.available_estimated is True


def test_meminfo_missing_required_fields_raises():
    with pytest.raises(ValueError):
        meminfo_to_memory(parse_meminfo("Buffers: 10 kB\n"))


def test_parse_stat_cpu_times_in_seconds():
    cpu, running, blocked = parse_stat(STAT, ticks_per_second=100)
    assert cpu.user == pytest.approx(10.0)
    assert cpu.idle == pytest.approx(80.0)
    assert cpu.steal == pytest.approx(0.05)
    # guest (9. alan) user içinde zaten sayıldığı için toplama eklenmez
    assert cpu.total == pytest.approx((1000 + 50 + 300 + 8000 + 100 + 10 + 20 + 5) / 100)
    assert (running, blocked) == (3, 1)


def test_parse_stat_old_kernel_short_cpu_line():
    cpu, running, blocked = parse_stat("cpu 1 2 3 4\n", ticks_per_second=1)
    assert (cpu.user, cpu.idle, cpu.iowait, cpu.steal) == (1.0, 4.0, 0.0, 0.0)
    assert running is None and blocked is None


def test_parse_stat_without_cpu_line_raises():
    with pytest.raises(ValueError):
        parse_stat("ctxt 1\n")


def test_parse_vmstat_missing_keys_are_none():
    vm = parse_vmstat(VMSTAT)
    assert (vm.pswpin, vm.pswpout, vm.pgmajfault, vm.pgfault) == (300, 400, 2000, 1_000_000)
    partial = parse_vmstat("pgfault 5\n")
    assert partial.pswpin is None and partial.pgmajfault is None and partial.pgfault == 5


def test_parse_diskstats_and_physical_disk_filter():
    disks = parse_diskstats(DISKSTATS)
    assert disks["nvme0n1"].read_bytes == 20000 * 512
    assert disks["nvme0n1"].write_bytes == 40000 * 512
    assert disks["nvme0n1"].busy_ms == 900
    assert disks["sda"].busy_ms == 2  # 11 alanlı eski biçim
    block = ["nvme0n1", "sda", "loop0", "dm-0"]
    physical = sorted(n for n in disks if is_physical_disk(n, block))
    assert physical == ["nvme0n1", "sda"]
    # /sys/block okunamazsa ad kalıbıyla aynı sonuç
    assert sorted(n for n in disks if is_physical_disk(n)) == ["nvme0n1", "sda"]


def test_parse_pressure_some_and_full():
    assert parse_pressure("some avg10=1.50 avg60=0 avg300=0 total=1\n"
                          "full avg10=0.25 avg60=0 avg300=0 total=1\n") == \
        {"some": 1.5, "full": 0.25}
    assert parse_pressure("") == {}


def test_reader_reads_fake_tree(fake_proc):
    proc, sysfs = fake_proc
    reader = ProcFsReader(str(proc), str(sysfs), ticks_per_second=100)
    cpu, running, _ = reader.read_cpu()
    assert cpu.user == pytest.approx(10.0) and running == 3
    assert reader.read_memory().available == 2_000_000 * 1024
    assert reader.read_vm().pgmajfault == 2000
    assert sorted(reader.read_disks()) == ["nvme0n1", "sda"]
    assert reader.read_load1() == pytest.approx(0.52)
    psi = reader.read_pressure()
    assert psi.memory_some == 1.5 and psi.memory_full == 0.5 and psi.io_some == 2.0
    assert psi.cpu_some is None  # dosya yok: özellik algılama


def test_reader_without_psi_returns_none(fake_proc):
    proc, sysfs = fake_proc
    for f in (proc / "pressure").iterdir():
        f.unlink()
    assert ProcFsReader(str(proc), str(sysfs)).read_pressure() is None


def test_reader_opens_files_read_only(fake_proc, monkeypatch):
    proc, sysfs = fake_proc
    modes = []
    real_open = builtins.open

    def spy(path, mode="r", *args, **kwargs):
        modes.append((str(path), mode))
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    reader = ProcFsReader(str(proc), str(sysfs))
    reader.read_cpu(), reader.read_memory(), reader.read_vm(), reader.read_disks()
    reader.read_load1(), reader.read_pressure()
    assert modes, "hiç dosya açılmadı"
    assert all(mode == "r" for _path, mode in modes), modes


def test_clock_ticks_is_positive():
    assert procfs.clock_ticks_per_second() > 0
