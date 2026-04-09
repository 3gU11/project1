import os
import tempfile
import streamlit as st
from config import OCR_AVAILABLE, PaddleOCR, pdfplumber, docx

try:
    import cv2
except ImportError:
    cv2 = None

class OCRProcessor:
    def __init__(self):
        pass

    @staticmethod
    @st.cache_resource(show_spinner="正在加载AI模型，首次运行可能需要几分钟...")
    def get_ocr_model():
        """
        使用 Streamlit 的缓存机制加载模型，防止每次刷新页面都重新加载
        """
        if not OCR_AVAILABLE: return None
        return PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

    def process_file(self, uploaded_file):
        """处理上传的文件流"""
        if not OCR_AVAILABLE:
            return None, "OCR 依赖未安装"
            
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        
        # 创建临时文件保存上传的数据（因为PaddleOCR和Docx需要文件路径）
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            temp_file.write(uploaded_file.read())
            temp_path = temp_file.name

        full_text = ""
        try:
            if file_ext == '.docx':
                full_text = self._read_docx(temp_path)
            elif file_ext == '.doc':
                full_text = self._read_doc(temp_path)
            elif file_ext == '.pdf':
                full_text = self._read_pdf(temp_path)
            elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp']:
                full_text = self._ocr_image(temp_path)
            else:
                return None, "不支持的文件格式"
        except Exception as e:
            return None, str(e)
        finally:
            # 清理临时文件
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
        
        # 重置文件指针，以便后续保存
        uploaded_file.seek(0)

        # 解析字段
        parsed_data = self._parse_fields(full_text)
        return parsed_data, full_text

    def _read_doc(self, path):
        try:
            import win32com.client
            import pythoncom
        except ImportError:
            return "读取 .doc 文件需要安装 pywin32 库 (pip install pywin32) 且系统需安装 Microsoft Word。"

        pythoncom.CoInitialize()
        word = None
        doc = None
        text_content = ""
        try:
            # 使用 DispatchEx 强制启动新实例，避免影响用户当前打开的 Word
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = False
            
            abs_path = os.path.abspath(path)
            doc = word.Documents.Open(abs_path)
            
            # 读取全文
            text_content = doc.Content.Text
            
        except Exception as e:
            text_content = f"读取 .doc 失败: {str(e)}"
        finally:
            if doc:
                try:
                    doc.Close(False)
                except:
                    pass
            if word:
                try:
                    word.Quit()
                except:
                    pass
            pythoncom.CoUninitialize()
            
        return text_content


    def _read_docx(self, path):
        doc = docx.Document(path)
        text = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                text.append(" ".join([cell.text for cell in row.cells]))
        return "\n".join(text)

    def _read_pdf(self, path):
        text_content = ""
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text_content += extracted + "\n"
        # 注意：如果PDF是纯图扫描件，pdfplumber提取为空，这里为了演示简化，
        # 实际生产建议检测文本长度，如果过短则调用 pdf2image 转图后再 OCR
        if len(text_content) < 10: 
            return "[提示] 这是一个扫描版PDF，本基础版本暂仅支持文字版PDF提取。"
        return text_content

    def _ocr_image(self, path):
        if cv2 is None:
            return "OCR 图像处理依赖未安装: cv2"
        ocr = self.get_ocr_model()
        
        # 1. 图像预处理 (增强识别率)
        try:
            image = cv2.imread(path)
            if image is None:
                return f"[错误] 无法读取图片: {path}"
                
            # 灰度化
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # 去噪 (高斯模糊)
            denoised = cv2.GaussianBlur(gray, (5, 5), 0)
            
            # 二值化 (自适应阈值，处理光照不均)
            # thresh = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            
            # 对于合同文档，通常简单的二值化或者保持原图（PaddleOCR内部有处理）即可
            # 但如果图片质量差，适当的锐化有帮助
            # 这里我们尝试保留原图给Paddle，因为PaddleOCR内部集成了很强的预处理
            # 仅当原图识别失败时，可以考虑预处理。
            # 为了稳妥，我们先传原图路径。如果用户反馈有问题，可能是分辨率过大或过小。
            
            # PaddleOCR 建议输入是 numpy array
            result = ocr.ocr(image, cls=True)
            
        except Exception as e:
            return f"[错误] 图片预处理失败: {str(e)}"

        text_lines = []
        if result and result[0]:
            # 按垂直坐标排序，尽可能还原阅读顺序
            # PaddleOCR result: [[[x,y], [x,y]...], (text, conf)]
            # sort by y coordinate of the first point box[0][1]
            sorted_res = sorted(result[0], key=lambda x: x[0][0][1])
            
            for line in sorted_res:
                txt = line[1][0]
                conf = line[1][1]
                if conf > 0.5: # 过滤低置信度
                    text_lines.append(txt)
        else:
            return "[警告] 未识别到有效文字 (可能是图片模糊或方向不对)"
            
        return "\n".join(text_lines)

    def _parse_fields(self, text):
        """字段提取逻辑：正则 + LLM"""
        # 1. 尝试使用 LLM 进行智能提取
        llm_data = self._extract_with_llm(text)
        if llm_data:
            return llm_data
            
        # 2. 如果 LLM 失败，回退到正则规则提取
        st.warning("AI 提取失败，正在使用规则提取...")
        return self._parse_fields_regex(text)

    def _extract_with_llm(self, text):
        """使用大模型进行结构化提取"""
        api_key = "sk-b8ebeee6dc8b4d7eaae1e2502ddf3ff9"
        base_url = "https://api.deepseek.com/chat/completions"
        
        # 截取文本以避免超过 Context Window (保留前 3000 字通常足够)
        truncated_text = text[:3000]
        
        prompt = f"""
        我将提供一段OCR识别的文本（通常是合同或订单），请从中提取以下字段并以JSON格式返回：
        
        {{
            "customer": "需方/客户名称",
            "agent": "代理商（如果有）",
            "deadline": "交货日期/要求交期（格式：YYYY-MM-DD）",
            "global_note": "合同总备注/其他重要条款",
            "items": [
                {{
                    "model": "机型名称（请去除数量等无关字符）",
                    "qty": 数量（整数）,
                    "is_high": true/false（如果包含'加高'字样则为true）,
                    "note": "单行备注（针对该机型的特殊要求）"
                }}
            ]
        }}
        
        注意事项：
        1. 如果未找到某个字段，请填 null 或空字符串，不要填 "未识别"。
        2. "机型"如果是表格形式，请仔细解析每一行。
        3. "加高"通常出现在机型名称后或备注中。
        4. 请只返回纯 JSON，不要包含 markdown 标记。
        
        文本内容如下：
        {truncated_text}
        """
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": "deepseek-chat", # DeepSeek 官方 API 模型名通常为 deepseek-chat 或 deepseek-reasoner
            "messages": [
                {"role": "system", "content": "你是一个智能文档分析助手，擅长从OCR文本中提取结构化合同数据。只返回纯 JSON 格式的数据。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 1000,
            "stream": False
        }
        
        try:
            response = requests.post(base_url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                res_json = response.json()
                content = res_json['choices'][0]['message']['content']
                # 清洗 markdown 代码块标记
                content = content.replace("```json", "").replace("```", "").strip()
                return json.loads(content)
            else:
                print(f"API Error: {response.text}")
                return None
        except Exception as e:
            print(f"LLM Error: {e}")
            return None

    def _parse_fields_regex(self, text):
         # 简单兜底
         return {'需方': '未识别', '机型及数量': '未识别', '地址': '未识别', '交货日期': '未识别'}
