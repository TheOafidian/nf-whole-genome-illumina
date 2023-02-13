#!/usr/bin/env python3

import os
import argparse
from pathlib import Path
import pandas as pd

from utils import generate_uqid

CORR_SAMPLESHEET = "samplesheet.tsv"
DEF_SAMPLE_ID = "ID"
DEF_FW_READS = "fw_reads"
DEF_RV_READS = "rv_reads"


class SampleSheet:
    def __init__(
        self,
        samplesheet = CORR_SAMPLESHEET,
        sample_col = DEF_SAMPLE_ID,
        fw_col=DEF_FW_READS,
        rev_col=DEF_RV_READS,
        sample_db_dir=None,
        run_id=None,
    ) -> None:
        self.sample_col = sample_col
        self.fw_col = fw_col
        self.rev_col = rev_col
        self.run_id = run_id
        if sample_db_dir is not None:
            self.corrected_sheet = True
            self.sample_db_samplesheet = os.path.join(sample_db_dir, "sampledb.tsv")
            self.filename = os.path.join(os.path.dirname(samplesheet), CORR_SAMPLESHEET)
            samples_db_dir_path = Path(sample_db_dir)

            if not samples_db_dir_path.exists():
                os.makedirs(samples_db_dir_path, exist_ok=True)
        else:
            self.filename = samplesheet
            self.corrected_sheet = False
        

    def read_samplesheet(self):

        if self.filename.endswith(".tsv"):
            smpsh = pd.read_table(self.filename)
            assert self.rev_col in smpsh.columns
        ## Asumption: it is a csv, could implement xlsx with pd.read_xlsx,
        ## But then need to supply pyopenxlsx dependency in docker...
        else:
            smpsh = pd.read_csv(self.filename)
        self.content = smpsh

    def update_samplesheet(self):
        # Update paths to absolute paths.
        self.content[[self.fw_col, self.rev_col]] = self.content[
            [self.fw_col, self.rev_col]
        ].apply(lambda x: self._fetch_filepath(x))

        # Add run_name as column
        self.content["run_id"] = self.run_id
        # Generate uqid
        self.content["uqid"] = (
            self.content[["run_id", self.fw_col, self.rev_col]]
            .sum(axis=1)
            .map(generate_uqid)
        )


        # Add resulting assembly path as column
        contig_path = f"/results/{self.sample_col}/assembly/contigs.fa"
        self.content["assembly"] = os.path.dirname(self.filename).split("/data")[0] + contig_path

        # Rename ID, rv_read, fw_read cols to fixed names
        self.content.rename(
            columns={
                self.sample_col: "ID",
                self.fw_col: "fw_reads",
                self.rev_col: "rv_reads",
            }
        )

    def write_samplesheet(self):
        self.content.to_csv(CORR_SAMPLESHEET, sep="\t", index=False)

    def update_sampledb(self):

        if Path(self.sample_db_samplesheet).exists():
            db_content = pd.read_csv(self.sample_db_samplesheet)
            db_content = db_content.append(
                self.content[~self.content["ID"].isin(db_content["ID"])],
                ignore_index=True,
            )

            db_content.to_csv(self.sample_db_samplesheet, sep="\t", index=False)
        else:
            self.content.to_csv(self.sample_db_samplesheet, sep="\t", index=False)

    def _fetch_filepath(self, read_files):
        def simplify_samplenames(filenames: pd.Series) -> pd.Series:
            return filenames.apply(
                lambda x: x.lower().split(".")[0].split("/")[-1].strip()
            )

        def simplify_samplename(filename: str) -> str:
            return filename.lower().split(".")[0].strip()

        def find_matching_file(filename, rootdir):
            for root, _, files in os.walk(rootdir):
                for file in files:
                    if simplify_samplename(file) == filename:
                        return os.path.join(root, file)
            raise FileNotFoundError(
                f"Could not locate the read specified as {filename}"
            )

        smpsh_dir = os.path.dirname(self.filename)
        reads_smp = simplify_samplenames(read_files)
        return reads_smp.apply(lambda x: find_matching_file(x, smpsh_dir))


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        prog="WGS Samplesheet Reader",
        description="Read WGS Samplesheets. Find samples listed and save to a masterfile.",
    )


    parser.add_argument("-s", "--samplesheet", default=CORR_SAMPLESHEET)
    parser.add_argument("-i", "--sample_column", default=DEF_SAMPLE_ID)
    parser.add_argument("-f", "--forward_column",  default=DEF_FW_READS)
    parser.add_argument("-r", "--reverse_column", default=DEF_RV_READS)
    parser.add_argument("-d", "--sample_db_dir", default=None)
    parser.add_argument("-n", "--run_name", default=None)

    args = parser.parse_args()
    smpsh = SampleSheet(
        args.samplesheet,
        args.sample_column,
        args.forward_column,
        args.reverse_column,
        args.sample_db_dir,
        args.run_name,
    )

    smpsh.read_samplesheet()

    # Run these at the start of the pipeline
    if not smpsh.corrected_sheet:
        smpsh.update_samplesheet()
        smpsh.write_samplesheet()
    else:
        # Run this when finished
        smpsh.update_sampledb()
