# Copyright 2007-2010 by Peter Cock.  All rights reserved.
# This code is part of the Biopython distribution and governed by its
# license.  Please see the LICENSE file that should have been included
# as part of this package.

"""Tests for SeqIO write module."""

import os
import unittest
import warnings
from io import BytesIO
from Bio._py3k import StringIO
from Bio import BiopythonWarning
from Bio import SeqIO
from Bio import AlignIO
from Bio.SeqRecord import SeqRecord
from Bio.Seq import Seq
from Bio import Alphabet


# List of formats including alignment only file formats we can read AND write.
# We don't care about the order
test_write_read_alignment_formats = sorted(SeqIO._FormatToWriter)
for format in sorted(AlignIO._FormatToWriter):
    if format not in test_write_read_alignment_formats:
        test_write_read_alignment_formats.append(format)
test_write_read_alignment_formats.remove("gb")  # an alias for genbank
test_write_read_alignment_formats.remove("fastq-sanger")  # an alias for fastq


# This is a list of three-tuples.  Each tuple contains a
# list of SeqRecord objects, a description (string), and
# a list of tuples for expected failures (each with a
# list of formats, exception type, exception message).
test_records = [
    ([], "zero records", {}),
    ([SeqRecord(Seq("CHSMAIKLSSEHNIPSGIANAL", Alphabet.generic_protein), id="Alpha"),
      SeqRecord(Seq("HNGFTALEGEIHHLTHGEKVAF", Alphabet.generic_protein), id="Gamma"),
      SeqRecord(Seq("DITHGVG", Alphabet.generic_protein), id="delta")],
     "three peptides of different lengths", []),
    ([SeqRecord(Seq("CHSMAIKLSSEHNIPSGIANAL", Alphabet.generic_protein), id="Alpha"),
      SeqRecord(Seq("VHGMAHPLGAFYNTPHGVANAI", Alphabet.generic_protein), id="Beta"),
      SeqRecord(Seq("HNGFTALEGEIHHLTHGEKVAF", Alphabet.generic_protein), id="Gamma")],
     "three proteins alignment", []),
    ([SeqRecord(Seq("AATAAACCTTGCTGGCCATTGTGATCCATCCA", Alphabet.generic_dna), id="X"),
      SeqRecord(Seq("ACTCAACCTTGCTGGTCATTGTGACCCCAGCA", Alphabet.generic_dna), id="Y"),
      SeqRecord(Seq("TTTCCTCGGAGGCCAATCTGGATCAAGACCAT", Alphabet.generic_dna), id="Z")],
     "three DNA sequence alignment", []),
    ([SeqRecord(Seq("AATAAACCTTGCTGGCCATTGTGATCCATCCA", Alphabet.generic_dna), id="X",
                name="The\nMystery\rSequece:\r\nX"),
      SeqRecord(Seq("ACTCAACCTTGCTGGTCATTGTGACCCCAGCA", Alphabet.generic_dna), id="Y",
                description="an%sevil\rdescription right\nhere" % os.linesep),
      SeqRecord(Seq("TTTCCTCGGAGGCCAATCTGGATCAAGACCAT", Alphabet.generic_dna), id="Z")],
     "3 DNA seq alignment with CR/LF in name/descr",
     [(["genbank"], ValueError, r"Invalid whitespace in 'The\nMystery\rSequece:\r\nX' for LOCUS line"),
      (["mauve"], ValueError, "Sequences have different lengths, or repeated identifier")]),
    ([SeqRecord(Seq("CHSMAIKLSSEHNIPSGIANAL", Alphabet.generic_protein), id="Alpha"),
      SeqRecord(Seq("VHGMAHPLGAFYNTPHGVANAI", Alphabet.generic_protein), id="Beta"),
      SeqRecord(Seq("VHGMAHPLGAFYNTPHGVANAI", Alphabet.generic_protein), id="Beta"),
      SeqRecord(Seq("HNGFTALEGEIHHLTHGEKVAF", Alphabet.generic_protein), id="Gamma")],
     "alignment with repeated record",
     [(["stockholm"], ValueError, "Duplicate record identifier: Beta"),
      (["maf"], ValueError, "Identifiers in each MultipleSeqAlignment must be unique"),
      (["phylip", "phylip-relaxed", "phylip-sequential"], ValueError, "Repeated name 'Beta' (originally 'Beta'), possibly due to truncation")]),
    ]
# Meddle with the annotation too:
assert test_records[4][1] == "3 DNA seq alignment with CR/LF in name/descr"
# Add a list of strings,
test_records[4][0][2].annotations["note"] = [
    "Note%salso" % os.linesep + "\r\nhas\n evil line\rbreaks!", "Wow"]
# Add a simple string
test_records[4][0][2].annotations["comment"] = (
    "More%sof" % os.linesep + "\r\nthese\n evil line\rbreaks!")
# Add a float too:
test_records[4][0][2].annotations["weight"] = 2.5


class WriterTests(unittest.TestCase):
    """Cunning unit test where methods are added at run time."""

    def check(self, records, format):
        """General test function with with a little format specific information.

        This has some general expected exceptions hard coded!
        """
        # TODO - Check the exception messages?
        lengths = len({len(r) for r in records})
        if not records and format in ["stockholm", "phylip", "phylip-relaxed",
                                      "phylip-sequential", "nexus", "clustal",
                                      "sff", "mauve"]:
            self.check_write_fails(records, format, ValueError,
                                   "Must have at least one sequence")
        elif not records and format == "nib":
            self.check_write_fails(records, format, ValueError,
                                   "Must have one sequence")
        elif lengths > 1 and format in AlignIO._FormatToWriter:
            self.check_write_fails(records, format, ValueError,
                                   "Sequences must all be the same length")
        elif len(records) > 1 and format == "nib":
            self.check_write_fails(records, format, ValueError,
                                   "More than one sequence found")
        elif records and format in ["fastq", "fastq-sanger", "fastq-solexa",
                                    "fastq-illumina", "qual", "phd"]:
            self.check_write_fails(records, format, ValueError,
                                   "No suitable quality scores found in "
                                   "letter_annotations of SeqRecord "
                                   "(id=%s)." % records[0].id)
        elif records and format == "sff":
            self.check_write_fails(records, format, ValueError,
                                   "Missing SFF flow information")
        else:
            self.check_simple(records, format)

    def check_simple(self, records, format):
        if format in SeqIO._BinaryFormats:
            handle = BytesIO()
        else:
            handle = StringIO()
        count = SeqIO.write(records, handle, format)
        self.assertEqual(count, len(records))
        # Now read them back...
        handle.seek(0)
        new_records = list(SeqIO.parse(handle, format))
        self.assertEqual(len(new_records), len(records))
        for record, new_record in zip(records, new_records):
            # Using compare_record(record, new_record) is too strict
            if format == "nexus":
                # The nexus parser will dis-ambiguate repeated record ids.
                self.assertTrue(record.id == new_record.id or
                                new_record.id.startswith(record.id + ".copy"))
            else:
                self.assertEqual(record.id, new_record.id)
            self.assertEqual(str(record.seq), str(new_record.seq))
        handle.close()

    def check_write_fails(self, records, format, err_type, err_msg=""):
        if format in SeqIO._BinaryFormats:
            handle = BytesIO()
        else:
            handle = StringIO()
        if err_msg:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", BiopythonWarning)
                    SeqIO.write(records, handle, format)
            except err_type as err:
                self.assertEqual(str(err), err_msg)
        else:
            self.assertRaises(err_type, SeqIO.write, records, handle, format)
        handle.close()

    def test_bad_handle(self):
        handle = os.devnull
        record = SeqRecord(Seq("CHSMAIKLSSEHNIPSGIANAL", Alphabet.generic_protein), id="Alpha")
        records = [record]
        format = "fasta"
        # These deliberately mix up the handle and record order:
        self.assertRaises(TypeError, SeqIO.write, handle, record, format)
        self.assertRaises(TypeError, SeqIO.write, handle, records, format)
        self.assertEqual(1, SeqIO.write(records, handle, format))


for (records, descr, errs) in test_records:
    for format in test_write_read_alignment_formats:
        # Assume no errors expected...
        def funct(records, format, descr):
            f = lambda x: x.check(records, format)  # noqa: E731
            f.__doc__ = "%s for %s" % (format, descr)
            return f
        setattr(WriterTests,
                "test_%s_%s" % (format, descr.replace(" ", "_")),
                funct(records, format, descr))
        # Replace the method with an error specific one?
        for err_formats, err_type, err_msg in errs:
            if format in err_formats:
                def funct_e(records, format, descr, err_type, err_msg):
                    f = lambda x: x.check_write_fails(  # noqa: E731
                        records,
                        format,
                        err_type,
                        err_msg)
                    f.__doc__ = "%s for %s" % (format, descr)
                    return f
                setattr(WriterTests,
                        "test_%s_%s" % (format, descr.replace(" ", "_")),
                        funct_e(records, format, descr, err_type, err_msg))
                break
        del funct

if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    unittest.main(testRunner=runner)
