# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: annotation_data.proto
"""Generated protocol buffer code."""
import od3d.datasets.objectron.schema.a_r_capture_metadata_pb2 as a__r__capture__metadata__pb2
import od3d.datasets.objectron.schema.object_pb2 as object__pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder

# @@protoc_insertion_point(imports)
# import a_r_capture_metadata_pb2 as a__r__capture__metadata__pb2
# import object_pb2 as object__pb2


_sym_db = _symbol_database.Default()


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b'\n\x15\x61nnotation_data.proto\x12\x12xeno.pursuit.proto\x1a\x1a\x61_r_capture_metadata.proto\x1a\x0cobject.proto"8\n\x11NormalizedPoint2D\x12\t\n\x01x\x18\x01 \x01(\x02\x12\t\n\x01y\x18\x02 \x01(\x02\x12\r\n\x05\x64\x65pth\x18\x03 \x01(\x02"*\n\x07Point3D\x12\t\n\x01x\x18\x01 \x01(\x02\x12\t\n\x01y\x18\x02 \x01(\x02\x12\t\n\x01z\x18\x03 \x01(\x02"\x87\x01\n\x11\x41nnotatedKeyPoint\x12\n\n\x02id\x18\x01 \x01(\x05\x12-\n\x08point_3d\x18\x02 \x01(\x0b\x32\x1b.xeno.pursuit.proto.Point3D\x12\x37\n\x08point_2d\x18\x03 \x01(\x0b\x32%.xeno.pursuit.proto.NormalizedPoint2D"s\n\x10ObjectAnnotation\x12\x11\n\tobject_id\x18\x01 \x01(\x05\x12\x38\n\tkeypoints\x18\x02 \x03(\x0b\x32%.xeno.pursuit.proto.AnnotatedKeyPoint\x12\x12\n\nvisibility\x18\x03 \x01(\x02"\xd5\x01\n\x0f\x46rameAnnotation\x12\x10\n\x08\x66rame_id\x18\x01 \x01(\x05\x12\x39\n\x0b\x61nnotations\x18\x02 \x03(\x0b\x32$.xeno.pursuit.proto.ObjectAnnotation\x12\x36\n\x06\x63\x61mera\x18\x03 \x01(\x0b\x32&.research.compvideo.arcapture.ARCamera\x12\x11\n\ttimestamp\x18\x04 \x01(\x01\x12\x14\n\x0cplane_center\x18\x05 \x03(\x02\x12\x14\n\x0cplane_normal\x18\x06 \x03(\x02"w\n\x08Sequence\x12+\n\x07objects\x18\x01 \x03(\x0b\x32\x1a.xeno.pursuit.proto.Object\x12>\n\x11\x66rame_annotations\x18\x02 \x03(\x0b\x32#.xeno.pursuit.proto.FrameAnnotationb\x06proto3',
)

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, "annotation_data_pb2", globals())
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    _NORMALIZEDPOINT2D._serialized_start = 87
    _NORMALIZEDPOINT2D._serialized_end = 143
    _POINT3D._serialized_start = 145
    _POINT3D._serialized_end = 187
    _ANNOTATEDKEYPOINT._serialized_start = 190
    _ANNOTATEDKEYPOINT._serialized_end = 325
    _OBJECTANNOTATION._serialized_start = 327
    _OBJECTANNOTATION._serialized_end = 442
    _FRAMEANNOTATION._serialized_start = 445
    _FRAMEANNOTATION._serialized_end = 658
    _SEQUENCE._serialized_start = 660
    _SEQUENCE._serialized_end = 779
# @@protoc_insertion_point(module_scope)
