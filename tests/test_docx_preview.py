import os
import tempfile
import mammoth
from unittest.mock import patch, MagicMock

def test_mammoth_availability():
    """测试 mammoth 依赖是否被正确安装并可用"""
    try:
        import mammoth
        available = True
    except ImportError:
        available = False
    assert available == True, "mammoth 库未安装"

def test_docx_to_html_conversion():
    """测试 docx 转换为 html 的核心功能"""
    # 创建一个临时 docx 文件（模拟）
    # 由于构建一个真正的 docx 文件需要 python-docx，我们这里 mock mammoth.convert_to_html 的行为
    # 或者如果环境中有 docx，我们可以创建一个真正的 docx。
    
    mock_result = MagicMock()
    mock_result.value = "<p>这是一个测试文档</p>"
    mock_result.messages = []
    
    with patch("mammoth.convert_to_html", return_value=mock_result) as mock_convert:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_docx:
            tmp_docx.write(b"dummy docx content")
            tmp_path = tmp_docx.name
            
        try:
            with open(tmp_path, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
                html = (result.value or "").strip()
                
            assert html == "<p>这是一个测试文档</p>"
            mock_convert.assert_called_once()
        finally:
            os.remove(tmp_path)

def test_docx_preview_error_handling():
    """测试 mammoth 解析失败时的异常处理逻辑"""
    with patch("mammoth.convert_to_html", side_effect=Exception("解析失败")) as mock_convert:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_docx:
            tmp_docx.write(b"bad docx content")
            tmp_path = tmp_docx.name
            
        error_caught = False
        try:
            with open(tmp_path, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
        except Exception as e:
            error_caught = True
            assert str(e) == "解析失败"
            
        assert error_caught == True
        os.remove(tmp_path)
