#!/usr/bin/env python3
"""A NIBArchive reader, for the half of Logic's localisation that lives in nibs.

Logic uses Base Internationalization: `Base.lproj/<screen>.nib` holds the ENGLISH interface, and
each `<locale>.lproj/<screen>.strings` holds that screen's translations keyed by `objectID.property`
(`164.title`, `169.headerCell.title`). So the nine translated locales are plain text and the
English is inside the nib — which is why an earlier pass could find `추가` and not `Add`, and
reported strings as absent from the bundle when only their English half was out of reach.

`ibtool --export-strings-file` is the supported way to get at this and it requires a full Xcode;
this host has Command Line Tools only, and a machine running CI has neither. So the container is
read directly.

Format, from the header of any Logic nib and the published description of the container:

    "NIBArchive"  uint32 formatVersion  uint32 coderVersion
    (count, offset) pairs for objects, keys, values, class names
    object     := varint classIndex, varint firstValueIndex, varint valueCount
    key        := varint length, UTF-8 bytes
    value      := varint keyIndex, uint8 type, payload
    class name := varint length, varint extraCount, int32[extraCount], NUL-terminated name

The varint is the part that bites: the high bit marks the LAST byte, not a continuation, which is
the opposite of the usual encoding. A parser written the usual way reads plausible-looking garbage
rather than failing, so `parse` checks the header counts against what it actually decoded.

References: matsmattsson/nibsqueeze NibArchive.md; MatrixEditor/nibarchive.
"""
import struct
import sys

MAGIC = b"NIBArchive"

# Value type tags.
T_INT8, T_INT16, T_INT32, T_INT64 = 0, 1, 2, 3
T_TRUE, T_FALSE, T_FLOAT, T_DOUBLE = 4, 5, 6, 7
T_DATA, T_NIL, T_OBJECT = 8, 9, 10


class NibError(Exception):
    """The file is not a NIBArchive, or its own header disagrees with its contents."""


def _varint(buf, pos):
    """(value, next_pos). The high bit marks the FINAL byte — not a continuation."""
    value = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise NibError("varint ran past the end of the archive")
        byte = buf[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            return value, pos
        shift += 7
        if shift > 63:
            raise NibError("varint longer than 64 bits — the encoding is being misread")


def parse(data):
    """{"objects":[...], "keys":[str], "values":[...], "classes":[str]} for one archive."""
    if data[:len(MAGIC)] != MAGIC:
        raise NibError("not a NIBArchive")
    head = struct.unpack_from("<10I", data, len(MAGIC))
    (_fmt, _coder, obj_n, obj_off, key_n, key_off,
     val_n, val_off, cls_n, cls_off) = head

    pos = obj_off
    objects = []
    for _ in range(obj_n):
        cls, pos = _varint(data, pos)
        first, pos = _varint(data, pos)
        count, pos = _varint(data, pos)
        objects.append({"class": cls, "first_value": first, "value_count": count})

    pos = key_off
    keys = []
    for _ in range(key_n):
        length, pos = _varint(data, pos)
        keys.append(data[pos:pos + length].decode("utf-8", "replace"))
        pos += length

    pos = val_off
    values = []
    for _ in range(val_n):
        key_index, pos = _varint(data, pos)
        vtype = data[pos]
        pos += 1
        if vtype == T_INT8:
            payload = struct.unpack_from("<b", data, pos)[0]; pos += 1
        elif vtype == T_INT16:
            payload = struct.unpack_from("<h", data, pos)[0]; pos += 2
        elif vtype == T_INT32:
            payload = struct.unpack_from("<i", data, pos)[0]; pos += 4
        elif vtype == T_INT64:
            payload = struct.unpack_from("<q", data, pos)[0]; pos += 8
        elif vtype == T_TRUE:
            payload = True
        elif vtype == T_FALSE:
            payload = False
        elif vtype == T_FLOAT:
            payload = struct.unpack_from("<f", data, pos)[0]; pos += 4
        elif vtype == T_DOUBLE:
            payload = struct.unpack_from("<d", data, pos)[0]; pos += 8
        elif vtype == T_DATA:
            length, pos = _varint(data, pos)
            payload = data[pos:pos + length]; pos += length
        elif vtype == T_NIL:
            payload = None
        elif vtype == T_OBJECT:
            payload = struct.unpack_from("<I", data, pos)[0]; pos += 4
        else:
            raise NibError(f"unknown value type {vtype} at offset {pos - 1}")
        values.append({"key": key_index, "type": vtype, "value": payload})

    pos = cls_off
    classes = []
    for _ in range(cls_n):
        length, pos = _varint(data, pos)
        extras, pos = _varint(data, pos)
        pos += 4 * extras
        name = data[pos:pos + length]
        classes.append(name.rstrip(b"\x00").decode("utf-8", "replace"))
        pos += length

    # The counts in the header are the only independent check available: a varint read the usual
    # way produces values that look fine and a stream that ends in the wrong place.
    if len(objects) != obj_n or len(keys) != key_n or len(values) != val_n or len(classes) != cls_n:
        raise NibError("decoded counts disagree with the header")
    return {"objects": objects, "keys": keys, "values": values, "classes": classes}


def strings_by_object(archive):
    """{object_index: {key: text}} for every string-bearing value.

    Strings arrive as `data` payloads; the ones that are UTF-8 text are the interface's own labels
    and the rest are archived binary. Decoding is attempted and failures are skipped rather than
    guessed at.
    """
    out = {}
    for index, obj in enumerate(archive["objects"]):
        start = obj["first_value"]
        for value in archive["values"][start:start + obj["value_count"]]:
            if value["type"] != T_DATA:
                continue
            raw = value["value"]
            if not raw or b"\x00" in raw[:1]:
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if not text.isprintable():
                continue
            out.setdefault(index, {})[archive["keys"][value["key"]]] = text
    return out


def _leaf(archive, index, depth=0):
    """Resolve one object index to a Python value, for the leaf classes a runtime attribute uses.

    Only the classes that actually appear as runtime-attribute values are handled -- NSString,
    NSNumber, NSNull. Anything else returns None rather than a placeholder string, because a
    placeholder would flow into an index and be cited as if it were Apple's data.
    """
    if depth > 4 or index is None or index >= len(archive["objects"]):
        return None
    obj = archive["objects"][index]
    classes, keys, values = archive["classes"], archive["keys"], archive["values"]
    name = classes[obj["class"]] if obj["class"] < len(classes) else None
    fields = {}
    for value in values[obj["first_value"]:obj["first_value"] + obj["value_count"]]:
        if value["key"] < len(keys):
            fields[keys[value["key"]]] = value
    if name == "NSString":
        payload = fields.get("NS.bytes")
        if payload and payload["type"] == T_DATA:
            try:
                return payload["value"].decode("utf-8")
            except UnicodeDecodeError:
                return None
        return None
    if name == "NSNumber":
        for key in ("NS.intval", "NS.boolval", "NS.doubleval", "NS.dblval", "NS.floatval"):
            if key in fields:
                return fields[key]["value"]
        return None
    return None


def _array_children(archive, index):
    if index is None or index >= len(archive["objects"]):
        return []
    obj = archive["objects"][index]
    span = archive["values"][obj["first_value"]:obj["first_value"] + obj["value_count"]]
    return [value["value"] for value in span if value["type"] == T_OBJECT]


def runtime_attributes(archive):
    """Yield (keyPath, value) for every user-defined runtime attribute in the archive.

    Interface Builder stores these as an `NSIBUserDefinedRuntimeAttributesConnector` holding two
    PARALLEL arrays, `NSKeyPaths` and `NSValues`. They are paired by position and by nothing else,
    so a reader that collects the two arrays separately loses the pairing entirely -- which is how
    `qhid` looked like an unattached list of strings the first time it was read here.
    """
    classes = archive["classes"]
    keys = archive["keys"]
    for obj in archive["objects"]:
        name = classes[obj["class"]] if obj["class"] < len(classes) else None
        if name != "NSIBUserDefinedRuntimeAttributesConnector":
            continue
        fields = {}
        for value in archive["values"][obj["first_value"]:obj["first_value"] + obj["value_count"]]:
            if value["key"] < len(keys):
                fields[keys[value["key"]]] = value
        paths, vals = fields.get("NSKeyPaths"), fields.get("NSValues")
        if not paths or not vals or paths["type"] != T_OBJECT or vals["type"] != T_OBJECT:
            continue
        path_children = _array_children(archive, paths["value"])
        value_children = _array_children(archive, vals["value"])
        for position, path_index in enumerate(path_children):
            key_path = _leaf(archive, path_index)
            if key_path is None:
                continue
            resolved = (_leaf(archive, value_children[position])
                        if position < len(value_children) else None)
            yield key_path, resolved


if __name__ == "__main__":
    for path in sys.argv[1:]:
        arch = parse(open(path, "rb").read())
        print(f"{path}: objects={len(arch['objects'])} keys={len(arch['keys'])} "
              f"values={len(arch['values'])} classes={len(arch['classes'])}")
