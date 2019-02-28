# Create your tests here.
from unittest import TestCase
from external.types import NamedTupleFactory
import json
from external.timeutils import iso_strptime, iso_utcz_strftime
import datetime
import pytz


class NamedTupleFactoryTest(TestCase):

    def setUp(self):
        super(NamedTupleFactoryTest, self).setUp()
        self.simple_type_factory = NamedTupleFactory("SimpleType", ["a","b"])
        self.nested_type_factory = NamedTupleFactory("NestedType", ["c", "simple"],
                                                     decoders={"simple": self.simple_type_factory})

        self.date_type_factory = NamedTupleFactory("DateType", ["e","t"],
                                                   decoders={"t": iso_strptime},
                                                   encoders={"t": iso_utcz_strftime})
        self.complex_type_factory = NamedTupleFactory("ComplexNestedType", ["f", "complex"],
                                                     decoders={"complex": self.date_type_factory})

    def test_that_a_dictionary_can_be_converted_into_a_namedtuple(self):
        some_dict = {"a": 1, "b": 2}
        my_instance = self.simple_type_factory(some_dict)
        self.assertEqual(my_instance.a, 1)
        self.assertEqual(my_instance.b, 2)

    def test_that_unspecified_keys_are_discarded(self):
        some_dict = {"a": 1, "b": 2, "c": 3}
        my_instance = self.simple_type_factory(some_dict)
        self.assertEqual(my_instance.a, 1)
        self.assertEqual(my_instance.b, 2)
        self.assertFalse(hasattr(my_instance, "c"))

    def test_that_nested_types_are_correctly_mapped(self):
        some_dict = {"c": 3, "simple": {"a": 1, "b": 2}}
        my_instance = self.nested_type_factory(some_dict)
        self.assertEqual(my_instance.c, 3)
        self.assertEqual(my_instance.simple.a, 1)
        self.assertEqual(my_instance.simple.b, 2)

    def test_that_json_serialized_values_are_compact(self):
        some_dict = {"c": 3, "simple": {"a": 1, "b": 2}}
        my_instance = self.nested_type_factory(some_dict)
        serialized = json.dumps(self.nested_type_factory.to_python(my_instance))
        original_serialized = json.dumps(some_dict)
        self.assertEqual(len(serialized), 11)
        self.assertLess(len(serialized), len(original_serialized))

    def test_that_nested_types_can_be_reconstituted_from_json(self):
        some_dict = {"c": 3, "simple": {"a": 1, "b": 2}}
        my_instance = self.nested_type_factory(some_dict)
        serialized = json.dumps(self.nested_type_factory.to_python(my_instance))
        deserialized = json.loads(serialized)
        reconstituted = self.nested_type_factory(deserialized)
        self.assertEqual(my_instance, reconstituted)

    def test_that_complex_types_can_be_decoded(self):
        some_dict = {"e": 1, "t": "2019-02-26T00:00:01Z"}
        my_instance = self.date_type_factory.from_python(some_dict)
        self.assertEqual(my_instance.e, 1)
        self.assertEqual(my_instance.t, datetime.datetime(2019, 2, 26, 0, 0, 1, tzinfo=pytz.timezone('utc')))

    def test_that_complex_types_can_be_encoded(self):
        some_dict = {"e": 1, "t": "2019-02-26T00:00:01Z"}
        my_instance = self.date_type_factory.from_python(some_dict)
        serializable = self.date_type_factory.to_python(my_instance)
        self.assertEqual(serializable.e, 1)
        self.assertEqual(serializable.t, "2019-02-26T00:00:01Z")

    def test_that_complex_nested_types_can_be_decoded(self):
        some_dict = {"f": 2, "complex":{"e": 1, "t": "2019-02-26T00:00:01Z"}}
        my_instance = self.complex_type_factory.from_python(some_dict)
        self.assertEqual(my_instance.f, 2)
        self.assertEqual(my_instance.complex.e, 1)
        self.assertEqual(my_instance.complex.t, datetime.datetime(2019, 2, 26, 0, 0, 1, tzinfo=pytz.timezone('utc')))

    def test_that_complex_nested_types_can_be_decoded_and_re_encoded(self):
        some_dict = {"f": 2, "complex":{"e": 1, "t": "2019-02-26T00:00:01Z"}}
        decoded = self.complex_type_factory.from_python(some_dict)
        serializable = self.complex_type_factory.to_python(decoded)
        self.assertEqual(serializable.f, 2)
        self.assertEqual(serializable.complex.e, 1)
        self.assertEqual(serializable.complex.t, "2019-02-26T00:00:01Z")
