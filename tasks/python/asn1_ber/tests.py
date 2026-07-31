import unittest

from solution import BerError, decode, decode_integer, decode_oid


def shape(tlv):
    """Réduit un TLV à des tuples : indépendant de l'implémentation choisie."""
    value = tlv.value
    if isinstance(value, (bytes, bytearray)):
        return (tlv.tag_class, tlv.constructed, tlv.tag_number, bytes(value))
    return (tlv.tag_class, tlv.constructed, tlv.tag_number, [shape(c) for c in value])


def h(text: str) -> bytes:
    return bytes.fromhex(text.replace(" ", ""))


SNMP_GET = h(
    "3026"
    "020100"
    "04067075626c6963"
    "a019"
    "0204 12345678"
    "020100"
    "020100"
    "300b"
    "3009"
    "0605 2b06010201"
    "0500"
)


class TestPrimitives(unittest.TestCase):
    def test_simple_integer(self):
        self.assertEqual(shape(decode(h("02 01 05"))), ("universal", False, 2, b"\x05"))

    def test_octet_string(self):
        self.assertEqual(
            shape(decode(h("04 06 70 75 62 6c 69 63"))),
            ("universal", False, 4, b"public"),
        )

    def test_null_has_empty_value(self):
        self.assertEqual(shape(decode(h("05 00"))), ("universal", False, 5, b""))


class TestConstructed(unittest.TestCase):
    def test_sequence_of_two_integers(self):
        self.assertEqual(
            shape(decode(h("30 06 02 01 01 02 01 02"))),
            (
                "universal",
                True,
                16,
                [
                    ("universal", False, 2, b"\x01"),
                    ("universal", False, 2, b"\x02"),
                ],
            ),
        )

    def test_empty_constructed(self):
        self.assertEqual(shape(decode(h("30 00"))), ("universal", True, 16, []))

    def test_nested_sequences(self):
        self.assertEqual(
            shape(decode(h("30 04 30 02 05 00"))),
            ("universal", True, 16, [("universal", True, 16, [("universal", False, 5, b"")])]),
        )


class TestLengthForms(unittest.TestCase):
    def test_long_form_one_octet(self):
        data = h("04 81 c8") + b"\xaa" * 200
        self.assertEqual(shape(decode(data)), ("universal", False, 4, b"\xaa" * 200))

    def test_long_form_two_octets(self):
        data = h("04 82 01 00") + b"\xbb" * 256
        self.assertEqual(shape(decode(data)), ("universal", False, 4, b"\xbb" * 256))

    def test_indefinite_length(self):
        data = h("24 80 04 03 61 62 63 04 02 64 65 00 00")
        self.assertEqual(
            shape(decode(data)),
            (
                "universal",
                True,
                4,
                [("universal", False, 4, b"abc"), ("universal", False, 4, b"de")],
            ),
        )

    def test_indefinite_nested_in_definite(self):
        data = h("30 0d 24 80 04 03 61 62 63 04 02 64 65 00 00")
        outer = decode(data)
        self.assertEqual(outer.tag_number, 16)
        self.assertEqual(len(outer.value), 1)
        self.assertEqual(len(outer.value[0].value), 2)


class TestTagForms(unittest.TestCase):
    def test_context_class_constructed(self):
        self.assertEqual(shape(decode(h("a0 00"))), ("context", True, 0, []))

    def test_application_class(self):
        self.assertEqual(shape(decode(h("40 01 07"))), ("application", False, 0, b"\x07"))

    def test_private_class(self):
        self.assertEqual(shape(decode(h("c0 01 07"))), ("private", False, 0, b"\x07"))

    def test_high_tag_number_31(self):
        self.assertEqual(shape(decode(h("bf 1f 00"))), ("context", True, 31, []))

    def test_high_tag_number_128(self):
        self.assertEqual(shape(decode(h("9f 81 00 01 aa"))), ("context", False, 128, b"\xaa"))


class TestErrors(unittest.TestCase):
    def test_empty_input(self):
        with self.assertRaises(BerError):
            decode(b"")

    def test_truncated_content(self):
        with self.assertRaises(BerError):
            decode(h("02 05 01"))

    def test_trailing_bytes(self):
        with self.assertRaises(BerError):
            decode(h("02 01 05 00"))

    def test_indefinite_on_primitive(self):
        with self.assertRaises(BerError):
            decode(h("02 80 01 02 00 00"))

    def test_reserved_length_ff(self):
        with self.assertRaises(BerError):
            decode(h("02 ff 01"))

    def test_unterminated_indefinite(self):
        with self.assertRaises(BerError):
            decode(h("24 80 04 01 61"))

    def test_truncated_high_tag(self):
        with self.assertRaises(BerError):
            decode(h("9f 81"))

    def test_truncated_long_length(self):
        with self.assertRaises(BerError):
            decode(h("04 82 01"))


class TestDecodeInteger(unittest.TestCase):
    def test_positive_values(self):
        self.assertEqual(decode_integer(b"\x00"), 0)
        self.assertEqual(decode_integer(b"\x7f"), 127)
        self.assertEqual(decode_integer(b"\x00\x80"), 128)
        self.assertEqual(decode_integer(b"\x01\x00"), 256)

    def test_negative_values(self):
        self.assertEqual(decode_integer(b"\xff"), -1)
        self.assertEqual(decode_integer(b"\x80"), -128)
        self.assertEqual(decode_integer(b"\xff\x7f"), -129)

    def test_empty_is_error(self):
        with self.assertRaises(BerError):
            decode_integer(b"")


class TestDecodeOid(unittest.TestCase):
    def test_rsa_oid(self):
        self.assertEqual(decode_oid(h("2a 86 48 86 f7 0d")), "1.2.840.113549")

    def test_common_name_oid(self):
        self.assertEqual(decode_oid(h("55 04 03")), "2.5.4.3")

    def test_mib2_oid(self):
        self.assertEqual(decode_oid(h("2b 06 01 02 01")), "1.3.6.1.2.1")

    def test_first_arc_boundary(self):
        self.assertEqual(decode_oid(h("28")), "1.0")

    def test_second_arc_above_39(self):
        self.assertEqual(decode_oid(h("81 34")), "2.100")

    def test_empty_is_error(self):
        with self.assertRaises(BerError):
            decode_oid(b"")

    def test_unterminated_subidentifier(self):
        with self.assertRaises(BerError):
            decode_oid(h("2a 86"))


class TestSnmpPdu(unittest.TestCase):
    def test_overall_structure(self):
        pdu = decode(SNMP_GET)
        self.assertEqual((pdu.tag_class, pdu.constructed, pdu.tag_number), ("universal", True, 16))
        self.assertEqual(len(pdu.value), 3)
        version, community, request = pdu.value
        self.assertEqual(decode_integer(version.value), 0)
        self.assertEqual(community.value, b"public")
        self.assertEqual(
            (request.tag_class, request.constructed, request.tag_number),
            ("context", True, 0),
        )

    def test_request_fields(self):
        request = decode(SNMP_GET).value[2]
        request_id, error_status, error_index, varbinds = request.value
        self.assertEqual(decode_integer(request_id.value), 305419896)
        self.assertEqual(decode_integer(error_status.value), 0)
        self.assertEqual(decode_integer(error_index.value), 0)
        self.assertEqual(varbinds.tag_number, 16)

    def test_varbind_oid(self):
        varbind = decode(SNMP_GET).value[2].value[3].value[0]
        oid, null = varbind.value
        self.assertEqual(oid.tag_number, 6)
        self.assertEqual(decode_oid(oid.value), "1.3.6.1.2.1")
        self.assertEqual(null.tag_number, 5)
        self.assertEqual(null.value, b"")


if __name__ == "__main__":
    unittest.main()
