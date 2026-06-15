import io
import zipfile

from app import extract_text_from_file


def test_extract_txt_utf8():
    content = "辐射超标地面点位ID\n130\n".encode("utf-8")
    text = extract_text_from_file("report.txt", content)
    assert "130" in text


def test_extract_docx_xml_fallback_minimal_package():
    xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>辐射超标手套孔名称</w:t></w:r></w:p>
    <w:p><w:r><w:t>手套孔 1#</w:t></w:r></w:p>
  </w:body>
</w:document>'''.encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)

    out = extract_text_from_file("demo.docx", buf.getvalue())
    assert "手套孔" in out


def test_extract_docx_xml_fallback_with_table_tokens():
    xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:r><w:t>任务</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>结束</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>时间</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>：</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>2025-07-01</w:t></w:r></w:p></w:tc>
      </w:tr>
    </w:tbl>
  </w:body>
</w:document>'''.encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)

    out = extract_text_from_file("table.docx", buf.getvalue())
    assert "任务" in out
    assert "2025-07-01" in out
