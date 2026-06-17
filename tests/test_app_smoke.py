from streamlit.testing.v1 import AppTest


APP_TITLE = "辐照监测可视化与智能化分析系统"
STAGE_LABELS = ("数据导入", "空间总览", "趋势分析", "智能研判", "报告生成")


def test_streamlit_workbench_smoke():
    app = AppTest.from_file("app.py").run(timeout=30)

    assert not app.exception
    assert any(APP_TITLE in title.value for title in app.title)
    uploaders = app.get("file_uploader")
    assert len(uploaders) == 1
    assert [file_type.lstrip(".") for file_type in uploaders[0].proto.type] == ["xlsx"]

    markdown_text = "\n".join(markdown.value for markdown in app.markdown)
    assert all(label in markdown_text for label in STAGE_LABELS)
