
# ============================================================
# B机集成服务：接收文件 + 自动生成SQL + 自动比对入库
# 依赖：pip install flask pandas openpyxl xlrd pymysql
# 运行：python B_full_service.py
# ============================================================

import os
import re
import time
import shutil
import csv
import io
import json
import tempfile
import pymysql
import sys
import functools
from datetime import datetime
import pandas as pd
from flask import Flask, request, abort

# 强制 print 立即刷新缓冲区，确保日志实时显示
print = functools.partial(print, flush=True)

app = Flask(__name__)

# -------- 配置区 --------
# 接收文件配置
SAVE_DIR   = r"D:\ReceivedFiles"   # 原始文件保存目录（Windows）
SECRET_KEY = "your_secret_key_123" # 与A机保持一致
PORT       = 4800

# 自动处理配置
OUTPUT_DIR = r"D:\ReceivedOutputs" # 初步处理后的SQL保存目录
PROCESSED_DIR = os.path.join(SAVE_DIR, 'processed') # 原始文件处理后归档目录
ERROR_DIR = os.path.join(SAVE_DIR, 'error') # 处理失败文件归档目录

# 最终比对输出配置
FINAL_OUTPUT_DIR = r"D:\OutputDiffs" # 最终差异SQL保存目录

# 数据库配置文件路径
DB_CONFIG_FILE = "db_config.json"

# 确保目录存在
for d in [SAVE_DIR, OUTPUT_DIR, PROCESSED_DIR, ERROR_DIR, FINAL_OUTPUT_DIR]:
    os.makedirs(d, exist_ok=True)

# 允许的机型列表 (从 B_integrated.py 迁移)
ALLOWED_MODELS = [
    'FH-260C', 'FH-300C', 'FL-1180XS(PRO)', 'FL-1390XS(PRO)', 'FL-1390XS((PRO)', 'FL-1610XS',
    'FR-1080XS(PRO)', 'FR-1080Y', 'FR-1100XS(PRO)', 'FR-400AUTO', 'FR-400G', 'FR-400S', 'FR-400XS(PRO)',
    'FR-500AUTO', 'FR-500G', 'FR-500XS(PRO)', 'FR-600AUTO', 'FR-600G', 'FR-600MS', 'FR-600XS(PRO)',
    'FR-7055AUTO', 'FR-7055M', 'FR-7055XS(PRO)', 'FR-8055AUTO', 'FR-8055XS(PRO)', 'FR-8060XS(PRO)', 'FR-8060Y(PRO)',
    'FR-8060AUTO', 'FR-850MS', 'FT-400XS(PRO)', 'FT-600S', 'FT-7055S'
]

# ------------------------
# 第一阶段：文件接收与格式化 (原 B_integrated.py 逻辑)
# ------------------------

def sanitize_batch_number(batch_number):
    if not batch_number:
        return ''
    str_batch_number = str(batch_number).strip()
    
    # 1. 处理格式如 "202603第8批附加" -> "03-08附加"
    match = re.search(r'\d{4}(\d{2})第(\d+)批(.+)', str_batch_number)
    if match:
        month = match.group(1)
        batch = match.group(2).zfill(2)
        suffix = match.group(3)
        return f"{month}-{batch}{suffix}"

    # 2. 处理格式如 "202601第1批" -> "01-01"
    match = re.search(r'\d{4}(\d{2})第(\d+)批', str_batch_number)
    if match:
        month = match.group(1)
        batch = match.group(2).zfill(2)
        return f"{month}-{batch}"
        
    return str_batch_number

def normalize_brackets(value):
    if value is None:
        return ''
    text = str(value).strip()
    if not text:
        return ''
    text = text.replace('（', '(').replace('）', ')')
    text = text.replace('【', '(').replace('】', ')')
    text = text.replace('[', '(').replace(']', ')')
    return text

def split_model_and_remark(model):
    normalized_model = normalize_brackets(model)
    if not normalized_model:
        return '', ''

    model_chars = list(normalized_model)
    matched_allowed = ''
    matched_allowed_normalized = ''
    matched_len = -1

    for allowed in ALLOWED_MODELS:
        normalized_allowed = normalize_brackets(allowed)
        allowed_chars = list(normalized_allowed)
        compare_len = min(len(model_chars), len(allowed_chars))
        idx = 0
        while idx < compare_len and model_chars[idx].upper() == allowed_chars[idx].upper():
            idx += 1
        if idx == len(allowed_chars) and idx > matched_len:
            matched_allowed = allowed
            matched_allowed_normalized = normalized_allowed
            matched_len = idx

    if matched_allowed:
        remain = normalized_model[len(matched_allowed_normalized):].strip()
        return matched_allowed, remain

    match_xs = re.search(r'(FT|FR|FL|FH|SR)-(\d+)XS', normalized_model, flags=re.IGNORECASE)
    if match_xs:
        prefix = match_xs.group(1).upper()
        number = match_xs.group(2)
        mapped_model = f"{prefix}-{number}XS(PRO)"
        remain = normalized_model[len(match_xs.group(0)):].strip()
        return mapped_model, remain

    match = re.search(r'(FT|FR|FL|FH|SR)-(\d+)X(?!S)', normalized_model, flags=re.IGNORECASE)
    if match:
        prefix = match.group(1).upper()
        number = match.group(2)
        mapped_model = f"{prefix}-{number}XS(PRO)"
        remain = normalized_model[len(match.group(0)):].strip()
        return mapped_model, remain

    sr_match = re.search(r'SR-(\d+[A-Za-z]*)', normalized_model, flags=re.IGNORECASE)
    if sr_match:
        model_suffix = sr_match.group(1)
        mapped_model = f"FR-{model_suffix}"
        remain = normalized_model[len(sr_match.group(0)):].strip()
        return mapped_model, remain

    base_model = re.sub(r'[\(（\[【][^\)）\]】]*[\)）\]】]', '', normalized_model).strip()
    remain = ''
    if base_model and normalized_model.upper().startswith(base_model.upper()):
        remain = normalized_model[len(base_model):].strip()
    if not remain:
        bracket_match = re.search(r'\((.*?)\)', normalized_model)
        if bracket_match:
            remain = f"({bracket_match.group(1)})"
    return base_model, remain

def process_model(model):
    matched_model, _ = split_model_and_remark(model)
    return matched_model

def sanitize_sql_value(value):
    if pd.isna(value) or value is None:
        return 'NULL'
    str_value = str(value)
    escaped_value = str_value.replace("'", "''")
    sanitized_value = escaped_value.replace(";", "")
    return f"'{sanitized_value}'"

def format_date_value(value):
    """格式化日期为 YYYY/M/D 格式，只保留年月日，不补0"""
    if pd.isna(value) or value is None:
        return ''
        
    # 如果已经是 datetime 对象
    if isinstance(value, (pd.Timestamp, datetime)):
        # 不补0: %-m 和 %-d 在某些平台（如 Windows）可能不支持，改用 .month 和 .day
        return f"{value.year}/{value.month}/{value.day}"
            
    str_val = str(value).strip()
    if not str_val:
        return ''
    
    try:
        # 0. 尝试 Excel 序列号 (纯数字，且在合理范围内，比如 > 30000 对应 1982年以后)
        # 避免误判如 "2023" (年份) 为 Excel 序列号
        if str_val.replace('.', '', 1).isdigit():
            try:
                num_val = float(str_val)
                if 30000 < num_val < 60000:  # 限制范围 1982-2064，避免误判
                    # Excel 序列号转日期 (基准 1899-12-30)
                    dt = datetime(1899, 12, 30) + pd.Timedelta(days=num_val)
                    return f"{dt.year}/{dt.month}/{dt.day}"
            except Exception:
                pass

        # 1. 尝试常见格式解析 (优先匹配纯日期)
        for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y%m%d', '%Y.%m.%d', '%d-%b-%y']:
            try:
                dt = datetime.strptime(str_val, fmt)
                return f"{dt.year}/{dt.month}/{dt.day}"
            except ValueError:
                continue
                
        # 2. 尝试包含时间的格式 (截取年月日)
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S']:
            try:
                dt = datetime.strptime(str_val, fmt)
                return f"{dt.year}/{dt.month}/{dt.day}"
            except ValueError:
                continue
        
        # 3. 尝试正则提取 (作为最后的手段，处理不规范格式)
        # 3.1 匹配带分隔符 YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD
        match = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', str_val)
        if match:
            year, month, day = match.groups()
            return f"{year}/{int(month)}/{int(day)}"

        # 3.2 匹配纯数字 YYYYMMDD (如 20260312已发)
        # 限制为 8 位数字开头，且符合日期逻辑
        match = re.search(r'(\d{4})(\d{2})(\d{2})', str_val)
        if match:
            year, month, day = match.groups()
            if 1900 <= int(year) <= 2100 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                return f"{year}/{int(month)}/{int(day)}"
            
        return str_val
    except Exception:
        return str(value)

def process_raw_file(filepath):
    """
    处理接收到的原始文件(Excel/CSV)，生成初步的SQL文件
    """
    if not os.path.exists(filepath):
        print(f"文件不存在: {filepath}")
        return False, None

    filename = os.path.basename(filepath)
    print(f"正在初步处理文件: {filename}")
    
    try:
        # 使用原文件名加时间戳作为输出文件名
        timestamp = int(time.time() * 1000)
        output_filename = f"processed-{timestamp}.sql"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        file_ext = os.path.splitext(filename)[1].lower()
        data_rows = [] 
        
        if file_ext == '.csv':
            # 读取CSV
            lines = []
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                with open(filepath, 'r', encoding='gbk') as f:
                    lines = f.readlines()
            
            last_batch_number = ''
            for index, line in enumerate(lines):
                if not line.strip(): continue
                columns = line.strip().split(',')
                batch_number = columns[0].strip() if len(columns) > 0 else ''
                if index == 0: continue # Skip header
                
                if not batch_number:
                    batch_number = last_batch_number
                else:
                    last_batch_number = batch_number
                
                while len(columns) < 4: columns.append('')
                original_model = columns[1].strip() if len(columns) > 1 else ''
                serial_number = columns[2].strip() if len(columns) > 2 else ''
                arrival_date = columns[3].strip() if len(columns) > 3 else ''
                
                data_rows.append({
                    'batch_number': batch_number,
                    'original_model': original_model,
                    'serial_number': serial_number,
                    'arrival_date': arrival_date
                })
                
        elif file_ext in ['.xls', '.xlsx']:
            # 读取Excel
            engine = 'xlrd' if file_ext == '.xls' else 'openpyxl'
            df = pd.read_excel(filepath, header=None, engine=engine)
            last_batch_number = ''
            
            for index, row in df.iterrows():
                if row.isnull().all(): continue
                row_list = row.tolist()
                batch_number = str(row_list[0]).strip() if pd.notna(row_list[0]) else ''
                if index == 0: continue # Skip header
                
                if not batch_number:
                    batch_number = last_batch_number
                else:
                    last_batch_number = batch_number
                
                while len(row_list) < 4: row_list.append('')
                original_model = str(row_list[1]).strip() if pd.notna(row_list[1]) else ''
                serial_number = str(row_list[2]).strip() if pd.notna(row_list[2]) else ''
                arrival_date = row_list[3] if pd.notna(row_list[3]) else ''
                
                data_rows.append({
                    'batch_number': batch_number,
                    'original_model': original_model,
                    'serial_number': serial_number,
                    'arrival_date': arrival_date
                })
        else:
            print(f"不支持的文件格式: {filename}")
            return False, None
            
        # 生成SQL内容
        processed_lines = []
        for row in data_rows:
            sanitized_batch_number = sanitize_batch_number(row['batch_number'])
            processed_model, extracted_remark = split_model_and_remark(row['original_model'])
            
            # 格式化日期
            formatted_date = format_date_value(row.get('arrival_date', ''))
            
            original_model = row['original_model']
            remark = normalize_brackets(extracted_remark)
            normalized_original = normalize_brackets(original_model)
            normalized_processed = normalize_brackets(processed_model)
            if not remark and normalized_original and normalized_processed:
                if normalized_original.upper().startswith(normalized_processed.upper()):
                    remark = normalized_original[len(normalized_processed):].strip()
            for model in ALLOWED_MODELS:
                clean_model_str = normalize_brackets(model)
                escaped_model = re.escape(clean_model_str)
                remark = re.sub(escaped_model, '', remark, flags=re.IGNORECASE).strip()
            remark = re.sub(r'\(\s*PRO\s*\)', '', remark, flags=re.IGNORECASE).strip()
            remark = re.sub(r'PRO', '', remark, flags=re.IGNORECASE).strip()
            remark = re.sub(r'\(\s*\)', '', remark).strip()
            
            # 构建 VALUES
            # 注意：这里的字段名要与 csv_sql_converter_app.py 中的 key_fields 匹配
            # 假设 csv_sql_converter_app.py 默认用 "流水号,批次号"
            # 我们生成的 SQL 应该是 INSERT INTO table (批次号, 机型, 流水号, 预计入库时间, 机台备注/配置)
            values = [
                sanitize_sql_value(sanitized_batch_number),
                sanitize_sql_value(processed_model),
                sanitize_sql_value(row['serial_number']),
                sanitize_sql_value(formatted_date),
                sanitize_sql_value(remark)
            ]
            processed_lines.append(f"INSERT INTO finished_goods_data (批次号, 机型, 流水号, 预计入库时间, `机台备注/配置`) VALUES ({', '.join(values)});")
            
        # 写入文件
        # 注意：为了让 parse_sql_file 能解析，我们需要标准的 INSERT 格式
        # 这里的表名暂时写死为 finished_goods_data，或者应该从配置读取？
        # 为了兼容性，我们使用配置中的默认表名，或者在后续比对时统一
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(processed_lines))
            
        print(f"初步处理成功！已生成SQL文件: {output_path}")
        return True, output_path

    except Exception as e:
        print(f"初步处理失败: {str(e)}")
        return False, None

# ------------------------
# 第二阶段：数据库比对与差异生成 (原 csv_sql_converter_app.py 逻辑)
# ------------------------

def parse_sql_file(sql_file):
    """解析SQL文件，提取INSERT语句中的数据"""
    data = {}
    try:
        with open(sql_file, 'r', encoding='utf-8') as f:
            content = f.read()
            # 匹配INSERT语句
            insert_pattern = re.compile(r'INSERT\s+INTO\s+(\w+)\s+\((.*?)\)\s+VALUES\s+\((.*?)\);', re.IGNORECASE | re.DOTALL)
            matches = insert_pattern.findall(content)
            
            for match in matches:
                table_name = match[0]
                fields_str = match[1]
                values_str = match[2]
                
                try:
                    f_io = io.StringIO(fields_str)
                    reader = csv.reader(f_io, delimiter=',', skipinitialspace=True)
                    try: fields = next(reader)
                    except StopIteration: continue
                    
                    v_io = io.StringIO(values_str)
                    reader = csv.reader(v_io, quotechar="'", delimiter=',', skipinitialspace=True, doublequote=True)
                    try: values = next(reader)
                    except StopIteration: continue
                except Exception: continue

                if table_name not in data: data[table_name] = []
                if len(fields) == len(values):
                    data[table_name].append(dict(zip(fields, values)))
    except FileNotFoundError:
        print(f"未找到文件 {sql_file}")
    return data

def get_db_data(host, user, password, database, table_name):
    """从数据库获取数据"""
    data = {}
    try:
        connection = pymysql.connect(
            host=host, user=user, password=password, database=database,
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )
        with connection:
            with connection.cursor() as cursor:
                sql = f"SELECT * FROM `{table_name}`"
                cursor.execute(sql)
                result = cursor.fetchall()
                formatted_rows = []
                for row in result:
                    formatted_row = {}
                    for k, v in row.items():
                        formatted_row[k] = str(v) if v is not None else None
                    formatted_rows.append(formatted_row)
                data[table_name] = formatted_rows
    except Exception as e:
        print(f"数据库错误: {e}")
        return None
    return data

def normalize_value(val):
    """归一化值：处理None/NULL，去除空格，统一转大写，全角转半角以忽略格式差异"""
    if val is None: return ''
    s = str(val).strip()
    if s.upper() == 'NULL': return ''
    
    # 全角括号转半角括号
    s = s.replace('（', '(').replace('）', ')')
    
    return s.upper()

def compare_and_generate_diff(input_sql_data, existing_sql_data, extra_fields=None, key_fields=None):
    """比对逻辑：排除已存在的数据"""
    if extra_fields is None: extra_fields = []
    if key_fields is None: key_fields = []
    diff_sqls = []
    key_fields_lower = [k.lower() for k in key_fields]
    
    for table_name, input_rows in input_sql_data.items():
        existing_rows = existing_sql_data.get(table_name, [])
        
        # 如果没有key_fields，默认全部新增
        if not key_fields_lower:
             for input_row in input_rows:
                fields_str = ', '.join(input_row.keys())
                values_str = ', '.join(input_row.values())
                diff_sqls.append(f"INSERT INTO {table_name} ({fields_str}) VALUES ({values_str});")
             continue

        # 构建现有数据指纹
        existing_keys_set = set()
        if existing_rows:
            for row in existing_rows:
                row_lower = {k.lower(): v for k, v in row.items()}
                key_values = []
                missing_key = False
                for k in key_fields_lower:
                    if k in row_lower: 
                        key_values.append(normalize_value(row_lower[k]))
                    else: 
                        missing_key = True; break
                if not missing_key: existing_keys_set.add(tuple(key_values))
        
        # 过滤输入数据
        for input_row in input_rows:
            input_row_lower = {k.lower(): v for k, v in input_row.items()}
            key_values = []
            missing_key = False
            for k in key_fields_lower:
                if k in input_row_lower: 
                    key_values.append(normalize_value(input_row_lower[k]))
                else: missing_key = True; break
            
            should_exclude = False
            if not missing_key and tuple(key_values) in existing_keys_set:
                should_exclude = True
            
            if not should_exclude:
                fields = list(input_row.keys())
                values = []
                for f in fields:
                    val = input_row[f]
                    if val is None: values.append("NULL")
                    else:
                        v_esc = str(val).replace("'", "''")
                        values.append(f"'{v_esc}'")
                
                fields_str = ', '.join(fields)
                values_str = ', '.join(values)
                diff_sqls.append(f"INSERT INTO {table_name} ({fields_str}) VALUES ({values_str});")
    
    return diff_sqls

def process_diff_generation(sql_file_path):
    """执行第二阶段：比对并生成最终SQL"""
    print(f"开始第二阶段：数据库比对... ({sql_file_path})")
    
    # 默认配置
    config = {
        "host": "localhost", "user": "root", "password": "", 
        "database": "rjt3", "table": "finished_goods_data",
        "extra_fields": "", "key_fields": "机型,流水号"
    }
    
    # 读取配置
    if os.path.exists(DB_CONFIG_FILE):
        try:
            with open(DB_CONFIG_FILE, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                # 如果用户配置中没有显式设置 key_fields，则保持新默认值
                config.update(user_config)
        except Exception as e:
            print(f"读取配置失败: {e}")
    
    db_host = config.get("host")
    db_user = config.get("user")
    db_password = config.get("password")
    db_name = config.get("database")
    table_name = config.get("table")
    extra_fields = [f.strip() for f in config.get("extra_fields", "").replace('，', ',').split(',') if f.strip()]
    key_fields = [f.strip() for f in config.get("key_fields", "机型,流水号").replace('，', ',').split(',') if f.strip()]
    
    try:
        # 1. 解析刚才生成的SQL文件
        input_sql_data = parse_sql_file(sql_file_path)
        if not input_sql_data:
            print("警告：未解析到有效数据，跳过比对。")
            return
            
        # 2. 统一表名 (强制使用配置的表名)
        input_table_keys = list(input_sql_data.keys())
        if len(input_sql_data) == 1:
            src_table = input_table_keys[0]
            if src_table != table_name:
                print(f"将表名 '{src_table}' 映射为配置表名 '{table_name}'")
                input_sql_data[table_name] = input_sql_data.pop(src_table)
        
        # 3. 获取数据库数据
        existing_sql_data = get_db_data(db_host, db_user, db_password, db_name, table_name)
        if existing_sql_data is None: return

        # 兼容性处理：如果数据库返回的数据包含旧列名，则进行映射
        if existing_sql_data and table_name in existing_sql_data:
            rows = existing_sql_data[table_name]
            if rows:
                first_row = rows[0]
                # 检查是否需要映射
                need_map_model = '型号' in first_row and '机型' not in first_row
                need_map_remark = '备注' in first_row and '机台备注/配置' not in first_row
                
                if need_map_model or need_map_remark:
                    print(f"检测到旧列名，正在映射... (型号->机型: {need_map_model}, 备注->机台备注/配置: {need_map_remark})")
                    for row in rows:
                        if need_map_model: row['机型'] = row.pop('型号')
                        if need_map_remark: row['机台备注/配置'] = row.pop('备注')

        # 4. 生成差异
        print(f"正在进行比对: 数据库现有 {len(existing_sql_data.get(table_name, []))} 条数据")
        print(f"输入文件包含 {len(input_sql_data.get(table_name, []))} 条数据")
        print(f"使用的去重键: {key_fields}")
        diff_sqls = compare_and_generate_diff(input_sql_data, existing_sql_data, extra_fields, key_fields)
        
        # 5. 输出结果
        timestamp = int(time.time() * 1000)
        output_filename = f"diff-{timestamp}.sql"
        output_path = os.path.join(FINAL_OUTPUT_DIR, output_filename)
        
        if diff_sqls:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(diff_sqls))
            print(f"第二阶段完成！生成差异数据 {len(diff_sqls)} 条。")
            print(f"最终结果已保存: {output_path}")
            
            # 第三阶段：自动转 CSV
            convert_sql_to_csv(output_path)
            
            # 第四阶段：导入到 plan_import
            import_diff_to_plan_import(output_path)
        else:
            print("第二阶段完成！数据已同步，无差异数据。")
            
    except Exception as e:
        print(f"第二阶段处理出错: {e}")

# ------------------------
# 第三阶段：SQL 转 CSV (原 sql_to_csv.py 逻辑)
# ------------------------

def convert_sql_to_csv(sql_path):
    """将指定的 SQL 文件转换为 CSV 文件"""
    if not os.path.exists(sql_path):
        print(f"Error: File {sql_path} not found.")
        return False

    csv_path = sql_path.replace('.sql', '.csv')
    print(f"Converting {os.path.basename(sql_path)} -> {os.path.basename(csv_path)}...")
    
    try:
        with open(sql_path, 'r', encoding='utf-8') as f_in, \
             open(csv_path, 'w', newline='', encoding='utf-8-sig') as f_out:
            
            writer = None
            # 正则表达式用于匹配 INSERT 语句
            pattern = re.compile(r"INSERT INTO .*? \((.*?)\) VALUES \((.*)\);", re.IGNORECASE)
            
            processed_lines = 0
            for line_num, line in enumerate(f_in, 1):
                line = line.strip()
                if not line or not line.upper().startswith("INSERT INTO"):
                    continue
                    
                match = pattern.search(line)
                if match:
                    columns_str = match.group(1)
                    values_str = match.group(2)
                    
                    # 解析列名
                    if writer is None:
                        columns = [c.strip().strip('`') for c in columns_str.split(',')]
                        writer = csv.writer(f_out)
                        writer.writerow(columns)
                    
                    # 解析值
                    try:
                        reader = csv.reader([values_str], delimiter=',', quotechar="'", skipinitialspace=True, doublequote=True)
                        row = next(reader)
                        writer.writerow(row)
                        processed_lines += 1
                    except Exception as e:
                        print(f"  Warning: Error parsing values on line {line_num}: {e}")
            
            print(f"  Finished {os.path.basename(sql_path)}: {processed_lines} rows written.")
            return True
            
    except Exception as e:
        print(f"Error processing {os.path.basename(sql_path)}: {e}")
        return False

# ------------------------
# 第四阶段：导入差异数据到 plan_import (原 import_diffs_to_db.py 逻辑)
# ------------------------

def import_diff_to_plan_import(sql_path):
    print(f"开始第四阶段：导入数据到 plan_import... ({os.path.basename(sql_path)})")
    if not os.path.exists(sql_path):
        print(f"文件不存在: {sql_path}")
        return

    config = {"host": "localhost", "user": "root", "password": "", "database": "rjt3"}
    if os.path.exists(DB_CONFIG_FILE):
        try:
            with open(DB_CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            print(f"读取配置失败: {e}")

    target_table = "plan_import"
    pattern = re.compile(r"INSERT INTO .*? \((.*?)\) VALUES \((.*)\);", re.IGNORECASE)
    required_fields = ['批次号', '机型', '流水号']
    transient_error_codes = {1205, 1213, 2006, 2013}
    summary = {
        "total_insert_lines": 0,
        "parsed_rows": 0,
        "invalid_rows": 0,
        "duplicate_rows": 0,
        "to_import_rows": 0,
        "inserted_rows": 0,
        "failed_rows": 0
    }
    failed_records = []
    parsed_rows = []
    dedup_keys = set()

    with open(sql_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            raw_line = line.strip()
            if not raw_line.upper().startswith("INSERT INTO"):
                continue
            summary["total_insert_lines"] += 1
            match = pattern.search(raw_line)
            if not match:
                summary["invalid_rows"] += 1
                failed_records.append({"line_num": line_num, "reason": "SQL格式不匹配", "line": raw_line})
                continue
            columns = [c.strip().strip('`') for c in match.group(1).split(',')]
            try:
                reader = csv.reader([match.group(2)], delimiter=',', quotechar="'", skipinitialspace=True, doublequote=True)
                values = next(reader)
            except Exception as e:
                summary["invalid_rows"] += 1
                failed_records.append({"line_num": line_num, "reason": f"值解析失败: {e}", "line": raw_line})
                continue
            if len(columns) != len(values):
                summary["invalid_rows"] += 1
                failed_records.append({"line_num": line_num, "reason": "列值数量不一致", "line": raw_line})
                continue

            data = {}
            for idx, col in enumerate(columns):
                val = values[idx]
                if val is None:
                    data[col] = None
                else:
                    s = str(val).strip()
                    data[col] = None if s.upper() == "NULL" else s
            if '备注' in data and '机台备注/配置' not in data:
                data['机台备注/配置'] = data.pop('备注')
            if 'f4' not in data or data.get('f4') is None or str(data.get('f4')).strip() == '':
                data['f4'] = '待入库'

            missing_fields = [k for k in required_fields if normalize_value(data.get(k)) == '']
            if missing_fields:
                summary["invalid_rows"] += 1
                failed_records.append({"line_num": line_num, "reason": f"关键字段为空: {','.join(missing_fields)}", "line": raw_line})
                continue

            row_key = tuple(normalize_value(data.get(k)) for k in ['批次号', '机型', '流水号', '预计入库时间', '机台备注/配置'])
            if row_key in dedup_keys:
                summary["duplicate_rows"] += 1
                continue
            dedup_keys.add(row_key)
            parsed_rows.append({"line_num": line_num, "data": data, "line": raw_line})

    summary["parsed_rows"] = len(parsed_rows)
    summary["to_import_rows"] = len(parsed_rows)
    print(f"导入前校验: INSERT行={summary['total_insert_lines']} 解析成功={summary['parsed_rows']} 无效={summary['invalid_rows']} 重复={summary['duplicate_rows']}")

    if summary["to_import_rows"] == 0:
        print("没有可导入的有效数据，已终止导入以避免清空目标表。")
        if failed_records:
            fail_log_path = f"{sql_path}.plan_import_failures.log"
            with open(fail_log_path, 'w', encoding='utf-8') as lf:
                for item in failed_records:
                    lf.write(f"line={item['line_num']} reason={item['reason']} line={item['line']}\n")
            print(f"失败明细已写入: {fail_log_path}")
        return

    try:
        connection = pymysql.connect(
            host=config["host"],
            user=config["user"],
            password=config["password"],
            database=config["database"],
            charset='utf8mb4',
            autocommit=False,
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print(f"数据库连接失败: {e}")
        return

    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) AS cnt FROM `{target_table}`")
                before_count = int(cursor.fetchone().get('cnt', 0))
                print(f"导入前 {target_table} 记录数: {before_count}")

                try:
                    cursor.execute(f"TRUNCATE TABLE `{target_table}`")
                except Exception:
                    cursor.execute(f"DELETE FROM `{target_table}`")

                cursor.execute(
                    """
                    SELECT COLUMN_NAME, DATA_TYPE
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                    """,
                    (config["database"], target_table)
                )
                column_rows = cursor.fetchall() or []
                datetime_types = {'date', 'datetime', 'timestamp', 'time', 'year'}
                datetime_columns = {
                    row.get('COLUMN_NAME') for row in column_rows
                    if str(row.get('DATA_TYPE', '')).lower() in datetime_types
                }

                remark_column_ready = False
                for row in parsed_rows:
                    data = row["data"]
                    for col in list(data.keys()):
                        val = data.get(col)
                        if col in datetime_columns and val is not None and str(val).strip() == '':
                            data[col] = None
                    insert_cols = list(data.keys())
                    insert_vals = [data[c] for c in insert_cols]
                    placeholders = ', '.join(['%s'] * len(insert_cols))
                    cols_str = ', '.join([f"`{c}`" for c in insert_cols])
                    insert_sql = f"INSERT INTO `{target_table}` ({cols_str}) VALUES ({placeholders})"

                    inserted = False
                    last_error = None
                    for attempt in range(1, 4):
                        try:
                            cursor.execute(insert_sql, insert_vals)
                            summary["inserted_rows"] += 1
                            inserted = True
                            break
                        except Exception as e:
                            last_error = e
                            err_code = e.args[0] if hasattr(e, 'args') and len(e.args) > 0 else None
                            err_msg = str(e)
                            if "Unknown column" in err_msg and "机台备注/配置" in err_msg and not remark_column_ready:
                                try:
                                    cursor.execute(f"SHOW COLUMNS FROM `{target_table}` LIKE %s", ("机台备注/配置",))
                                    exists_row = cursor.fetchone()
                                    if not exists_row:
                                        cursor.execute(f"ALTER TABLE `{target_table}` ADD COLUMN `机台备注/配置` TEXT")
                                    remark_column_ready = True
                                    continue
                                except Exception as alter_e:
                                    last_error = alter_e
                            if err_code in transient_error_codes and attempt < 3:
                                try:
                                    connection.ping(reconnect=True)
                                except Exception:
                                    pass
                                time.sleep(0.2 * attempt)
                                continue
                            break

                    if not inserted:
                        summary["failed_rows"] += 1
                        failed_records.append({
                            "line_num": row["line_num"],
                            "reason": str(last_error),
                            "line": row["line"]
                        })

                cursor.execute(f"SELECT COUNT(*) AS cnt FROM `{target_table}`")
                current_count = int(cursor.fetchone().get('cnt', 0))
                expected_count = summary["inserted_rows"]
                if current_count != expected_count:
                    raise Exception(f"一致性校验失败: 当前表记录数={current_count}, 期望={expected_count}")
                connection.commit()
                print(f"第四阶段完成！导入目标={summary['to_import_rows']} 成功={summary['inserted_rows']} 失败={summary['failed_rows']}")
                print(f"导入后 {target_table} 记录数: {current_count}")
    except Exception as e:
        try:
            connection.rollback()
        except Exception:
            pass
        print(f"数据库操作失败，事务已回滚: {e}")
    finally:
        try:
            connection.close()
        except Exception:
            pass

    if failed_records:
        fail_log_path = f"{sql_path}.plan_import_failures.log"
        with open(fail_log_path, 'w', encoding='utf-8') as lf:
            for item in failed_records:
                lf.write(f"line={item['line_num']} reason={item['reason']} line={item['line']}\n")
        print(f"失败明细已写入: {fail_log_path}")

# ------------------------
# Flask 路由
# ------------------------

@app.route("/upload", methods=["POST"])
def upload():
    if request.headers.get("X-Secret-Key") != SECRET_KEY:
        abort(403)

    file = request.files.get("file")
    if not file:
        return {"status": "error", "msg": "no file"}, 400

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"{timestamp}_{file.filename}"
    save_path = os.path.join(SAVE_DIR, filename)
    file.save(save_path)

    print(f"\n[{datetime.now()}] 收到文件: {filename}")
    
    # 1. 第一阶段：初步处理 (Excel/CSV -> SQL)
    success, sql_file_path = process_raw_file(save_path)
    
    if success:
        # 移动原始文件到 processed
        dest = os.path.join(PROCESSED_DIR, filename)
        if os.path.exists(dest):
            base, ext = os.path.splitext(filename)
            dest = os.path.join(PROCESSED_DIR, f"{base}_{int(time.time())}{ext}")
        shutil.move(save_path, dest)
        
        # 2. 第二阶段：立即触发数据库比对 (SQL -> Diff SQL)
        process_diff_generation(sql_file_path)
        
        return {"status": "ok", "processed": True, "msg": "File processed and diff generated"}, 200
    else:
        # 移动到 error
        dest = os.path.join(ERROR_DIR, filename)
        if os.path.exists(save_path): shutil.move(save_path, dest)
        return {"status": "ok", "processed": False, "msg": "Processing failed"}, 200

@app.route("/ping", methods=["GET"])
def ping():
    return {"status": "alive"}, 200

if __name__ == "__main__":
    print(f"B机全栈服务已启动，监听端口 {PORT}")
    print(f"原始文件存入: {SAVE_DIR}")
    print(f"初步SQL存入: {OUTPUT_DIR}")
    print(f"最终差异SQL存入: {FINAL_OUTPUT_DIR}")

    # 启动时自动检查 D:\ReceivedOutputs 下是否有未处理的SQL文件
    print("正在检查现有文件...")
    try:
        # 1. 检查未转换的 CSV
        if os.path.exists(FINAL_OUTPUT_DIR):
            final_sqls = [f for f in os.listdir(FINAL_OUTPUT_DIR) if f.endswith('.sql')]
            for sql_file in final_sqls:
                sql_path = os.path.join(FINAL_OUTPUT_DIR, sql_file)
                csv_path = sql_path.replace('.sql', '.csv')
                if not os.path.exists(csv_path):
                    print(f"启动检查：发现未转换的 SQL 文件 {sql_file}，正在转换...")
                    convert_sql_to_csv(sql_path)
            
            # 1.5 确保最新差异 SQL 已同步到 plan_import
            if final_sqls:
                latest_sql_file = max(final_sqls, key=lambda x: os.path.getmtime(os.path.join(FINAL_OUTPUT_DIR, x)))
                latest_sql_path = os.path.join(FINAL_OUTPUT_DIR, latest_sql_file)
                print(f"启动检查：正在将最新差异 SQL {latest_sql_file} 同步到 plan_import...")
                import_diff_to_plan_import(latest_sql_path)

        # 2. 检查未处理的初步 SQL
        if os.path.exists(OUTPUT_DIR):
            sql_files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.sql')]
            if sql_files:
                # 找到最新的文件
                latest_file = max(sql_files, key=lambda x: os.path.getmtime(os.path.join(OUTPUT_DIR, x)))
                latest_file_path = os.path.join(OUTPUT_DIR, latest_file)
                print(f"启动检查：发现现有文件 {latest_file}，正在处理...")
                process_diff_generation(latest_file_path)
            else:
                print("启动检查：未发现现有初步 SQL 文件。")
        else:
            print(f"启动检查：目录 {OUTPUT_DIR} 不存在。")
    except Exception as e:
        print(f"启动检查出错: {e}")

    app.run(host="0.0.0.0", port=PORT)
