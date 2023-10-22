import logging
import subprocess

from trex.cli import add_file_logging
from trex.cli.run10x import run_trex


def diff(expected, actual, ignore=None, recursive=False):
    args = ["diff", "-u"]
    if recursive:
        args.append("-r")
    if ignore is not None:
        args += [f"-x{name}" for name in ignore]
    subprocess.run(args + [expected, actual]).check_returncode()


def bam_diff(expected_bam, actual_bam, tmp_path):
    expected_sam = tmp_path / "expected.sam"
    actual_sam = tmp_path / "actual.sam"
    with open(expected_sam, "w") as expected, open(actual_sam, "w") as actual:
        subprocess.run(["samtools", "view", "--no-PG", "-h", expected_bam], stdout=expected)
        subprocess.run(["samtools", "view", "--no-PG", "-h", actual_bam], stdout=actual)
    diff(expected_sam, actual_sam)


def test_run_trex(tmp_path):
    add_file_logging(tmp_path / "log.txt")
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    run_trex(
        tmp_path,
        keep_doublets=True,
        should_write_loom=True,
        should_write_umi_matrix=True,
        start=694,
        end=724,
        transcriptome_inputs=["tests/data/"],
        amplicon_inputs=[],
    )
    diff("tests/expected", tmp_path, ignore=["data.loom", "entries.bam"], recursive=True)
    bam_diff("tests/expected/entries.bam", tmp_path / "entries.bam", tmp_path)
