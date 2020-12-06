#!/user/env/bin python

# Copyright 2010-2013 by Peter Cock.
# All rights reserved.
# This code is part of the Biopython distribution and governed by its
# license.  Please see the LICENSE file that should have been included
# as part of this package.


##########################################################################
#                                                                  #######
#    06/02/2015:                                                   #######
#        - I picked out the bits and pieces of code needed         #######
#          to write BAM files, removed python 3.0 compatibility    #######
#                                                                  #######
##########################################################################

import zlib
import struct


class BgzfWriter:

    def __init__(self, filename=None, mode="w", file_obj=None, compress_level=6):
        if file_obj:
            assert filename is None
            handle = file_obj
        else:
            if "w" not in mode.lower() and "a" not in mode.lower():
                raise ValueError("Must use write or append mode, not %r" % mode)
            if "a" in mode.lower():
                handle = open(filename, "ab")
            else:
                handle = open(filename, "wb")
        self._text = "b" not in mode.lower()
        self._handle = handle
        self._buffer = b""
        self.compress_level = compress_level

    def _write_block(self, block):
        _bgzf_header = b"\x1f\x8b\x08\x04\x00\x00\x00\x00\x00\xff\x06\x00\x42\x43\x02\x00"
        start_offset = self._handle.tell()
        assert len(block) <= 65536
        # Giving a negative window bits means no gzip/zlib headers, -15 used in samtools
        c = zlib.compressobj(self.compress_level,
                             zlib.DEFLATED,
                             -15,
                             zlib.DEF_MEM_LEVEL,
                             0)
        compressed = c.compress(block) + c.flush()
        del c
        assert len(compressed) < 65536, "TODO - Didn't compress enough, try less data in this block"
        crc = zlib.crc32(block)
        # Should cope with a mix of Python platforms...
        if crc < 0:
            crc = struct.pack("<i", crc)
        else:
            crc = struct.pack("<I", crc)
        bsize = struct.pack("<H", len(compressed) + 25)  # includes -1
        crc = struct.pack("<I", zlib.crc32(block) & 0xffffffff)
        uncompressed_length = struct.pack("<I", len(block))
        data = _bgzf_header + bsize + compressed + crc + uncompressed_length
        self._handle.write(data)

    def write(self, data):
        if type(data) is str:
            data = data.encode('utf-8')
        data_len = len(data)
        if len(self._buffer) + data_len < 65536:
            self._buffer += data
            return
        else:
            self._buffer += data
            while len(self._buffer) >= 65536:
                self._write_block(self._buffer[:65536])
                self._buffer = self._buffer[65536:]

    def flush(self):
        while len(self._buffer) >= 65536:
            self._write_block(self._buffer[:65535])
            self._buffer = self._buffer[65535:]
        self._write_block(self._buffer)
        self._buffer = b""
        self._handle.flush()

    def close(self):
        """Flush data, write 28 bytes empty BGZF EOF marker, and close the BGZF file."""
        _bgzf_eof = b"\x1f\x8b\x08\x04\x00\x00\x00\x00\x00\xff\x06\x00\x42\x43\x02\x00\x1b\x00\x03\x00\x00\x00\x00\x00" \
                    b"\x00\x00\x00\x00"
        if self._buffer:
            self.flush()
        # samtools will look for a magic EOF marker, just a 28 byte empty BGZF block,
        # and if it is missing warns the BAM file may be truncated. In addition to
        # samtools writing this block, so too does bgzip - so we should too.
        self._handle.write(_bgzf_eof)
        self._handle.flush()
        self._handle.close()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()
