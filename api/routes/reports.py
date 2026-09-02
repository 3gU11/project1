"""
API routes for report generation
Provides endpoints for generating and downloading Excel reports
"""
from typing import Optional
from datetime import datetime
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
import io
from sqlalchemy import text

from api.routes.auth import get_current_user_token, get_current_operator_name
from crud.reports import (
    build_model_report_appendices,
    get_dealer_sales_summary,
    get_inbound_report_data,
    get_order_model_quantities,
    get_order_report_data,
    get_shipment_report_data,
    get_completion_report_data,
    get_completion_output_report_data,
    get_available_filters,
    serialize_model_report_appendices,
)
from crud.inbound_history import backfill_inbound_history_from_logs
from database import get_engine


def calculate_category_summary(summary_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate model category summary from summary dataframe
    Groups by model_family from model_dictionary
    """
    if summary_df.empty:
        return pd.DataFrame(columns=['机型大类', '数量', '占比'])

    # Get model dictionary to map model_name to model_family
    with get_engine().connect() as conn:
        model_dict_df = pd.read_sql(
            text("SELECT model_name, model_family FROM model_dictionary WHERE model_family IS NOT NULL AND model_family != ''"),
            conn
        )

    # Create a mapping dict
    model_to_family = dict(zip(model_dict_df['model_name'], model_dict_df['model_family']))

    # Add family column to summary_df
    summary_with_family = summary_df.copy()
    summary_with_family['机型大类'] = summary_with_family['机型'].map(lambda x: model_to_family.get(x, '其他'))

    # Group by family
    category_summary = summary_with_family.groupby('机型大类')['数量'].sum().reset_index()
    category_summary.columns = ['机型大类', '数量']

    # Calculate percentage
    total = category_summary['数量'].sum()
    if total > 0:
        category_summary['占比'] = category_summary['数量'].apply(lambda x: f"{(x/total*100):.2f}%")
    else:
        category_summary['占比'] = '0%'

    # Sort by quantity descending
    category_summary = category_summary.sort_values('数量', ascending=False)

    return category_summary


router = APIRouter(dependencies=[Depends(get_current_user_token)])


def _generate_excel_response(
    sheets: dict[str, pd.DataFrame],
    filename: str
) -> StreamingResponse:
    """
    Generate Excel file response using openpyxl with optimized column widths
    sheets: dict of {sheet_name: dataframe}
    """
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=sheet_name)

            # Get the worksheet to set column widths
            worksheet = writer.sheets[sheet_name]

            # Define column width mapping for different report types
            # Optimized for A4 landscape printing with clear visibility
            column_widths = {
                # 完工报表专用列宽（三列布局：机型-数量-占比）
                '列1': 35,  # 机型列，需要容纳长机型名称和备注
                '列2': 8,   # 数量列，只显示数字
                '列3': 12,  # 占比列，显示百分比

                # 生产台账报表列宽
                '完工日期': 11,
                '合同号': 15,
                '机型': 20,  # 加宽以容纳长机型名称
                '完工数量': 9,
                '客户': 13,
                '经销商': 13,
                '产线': 9,
                '批次号': 12,
                '平均生产时长(小时)': 15,

                # 明细表列宽
                '机台ID': 16,
                '排产时间': 13,
                '完工时间': 13,
                '生产时长(小时)': 12,
                '流水号': 16,

                # 入库/出货报表列宽
                '入库日期': 11,
                '出货日期': 11,
                '状态': 10,
                '订单号': 15,
                '库位': 10,
                '操作员': 10,
                '入库时间': 13,
                '出货数量': 9
            }

            # Apply column widths
            for idx, col in enumerate(df.columns, 1):
                col_letter = worksheet.cell(row=1, column=idx).column_letter
                # Use predefined width if available, otherwise auto-calculate
                if col in column_widths:
                    worksheet.column_dimensions[col_letter].width = column_widths[col]
                else:
                    # Default width calculation for other columns
                    max_length = len(str(col))
                    for cell in worksheet[col_letter]:
                        try:
                            cell_value = str(cell.value) if cell.value is not None else ""
                            # Calculate width considering Chinese characters (count as 2)
                            char_count = sum(2 if ord(c) > 127 else 1 for c in cell_value)
                            max_length = max(max_length, char_count)
                        except:
                            pass
                    # Set width with reasonable limits (min 8, max 25)
                    adjusted_width = min(max(max_length + 2, 8), 25)
                    worksheet.column_dimensions[col_letter].width = adjusted_width

    output.seek(0)

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    # Use URL-encoded filename for Chinese characters
    import urllib.parse
    encoded_filename = urllib.parse.quote(f"{filename}_{timestamp}.xlsx")

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    }

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )


@router.get("/inbound")
def generate_inbound_report(
    start_date: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
    model_type: str = Query("", description="机型筛选"),
    customer: str = Query("", description="客户筛选"),
    format: str = Query("json", description="返回格式: json 或 excel"),
    current_operator: str = Depends(get_current_operator_name),
):
    """
    入库报表 - Inbound Report
    追踪实际入库的机器（不含已绑定直接发货的机器）
    """
    try:
        # Validate date range
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="结束日期必须大于或等于开始日期")

        summary_df, detail_df = get_inbound_report_data(
            start_date, end_date, model_type, customer
        )

        if summary_df.empty and detail_df.empty:
            if format == "json":
                return {"data": [], "total": 0}
            raise HTTPException(status_code=404, detail="未找到符合条件的数据")

        # Return JSON format for preview
        if format == "json":
            return {
                "data": detail_df.to_dict('records'),
                "total": len(detail_df)
            }

        # Return Excel format for download
        sheets = {
            "汇总": summary_df,
            "明细": detail_df
        }

        return _generate_excel_response(sheets, f"入库报表_{start_date}_{end_date}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"报表生成失败: {str(e)}")


@router.get("/orders")
def generate_order_report(
    start_date: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
    customer: str = Query("", description="客户筛选"),
    dealer: str = Query("", description="代理商筛选"),
    status: str = Query("", description="订单状态: active/done/deleted"),
    format: str = Query("json", description="返回格式: json 或 excel"),
    current_operator: str = Depends(get_current_operator_name),
):
    """
    订单报表 - Order Report
    销售订单分析，包含履约状态
    """
    try:
        # Validate date range
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="结束日期必须大于或等于开始日期")

        # Validate status
        if status and status not in ['active', 'done', 'deleted']:
            raise HTTPException(status_code=400, detail="订单状态必须是 active, done 或 deleted")

        df = get_order_report_data(start_date, end_date, customer, dealer, status)

        if df.empty:
            if format == "json":
                return {"data": [], "total": 0}
            raise HTTPException(status_code=404, detail="未找到符合条件的数据")

        appendices = build_model_report_appendices(get_order_model_quantities(df))
        dealer_summary = get_dealer_sales_summary(df)

        # Return JSON format for preview
        if format == "json":
            return {
                "data": df.to_dict('records'),
                "total": len(df),
                "appendices": serialize_model_report_appendices(appendices),
                "dealer_summary": dealer_summary.to_dict("records"),
            }

        # Keep the business detail first, then append the analysis tables.
        sheets = {
            "订单报表": df,
            "代理商统计": dealer_summary,
            **appendices,
        }

        return _generate_excel_response(sheets, f"订单报表_{start_date}_{end_date}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"报表生成失败: {str(e)}")


@router.get("/shipments")
def generate_shipment_report(
    start_date: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
    customer: str = Query("", description="客户筛选"),
    dealer: str = Query("", description="代理商筛选"),
    model_type: str = Query("", description="机型筛选"),
    format: str = Query("json", description="返回格式: json 或 excel"),
    current_operator: str = Depends(get_current_operator_name),
):
    """
    出货报表 - Shipment Report
    出货历史追踪，包含历史和当前出货数据
    """
    try:
        # Validate date range
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="结束日期必须大于或等于开始日期")

        summary_df, detail_df = get_shipment_report_data(
            start_date, end_date, customer, dealer, model_type
        )

        if summary_df.empty and detail_df.empty:
            if format == "json":
                return {"data": [], "total": 0}
            raise HTTPException(status_code=404, detail="未找到符合条件的数据")

        appendices = build_model_report_appendices(
            summary_df.rename(columns={"出货数量": "数量"})[["机型", "数量"]]
            if not summary_df.empty
            else pd.DataFrame(columns=["机型", "数量"])
        )

        # Return JSON format for preview
        if format == "json":
            return {
                "data": summary_df.to_dict('records'),
                "total": len(summary_df),
                "appendices": serialize_model_report_appendices(appendices),
            }

        # Return Excel format for download
        sheets = {
            "汇总": summary_df,
            "明细": detail_df,
            **appendices,
        }

        return _generate_excel_response(sheets, f"出货报表_{start_date}_{end_date}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"报表生成失败: {str(e)}")


@router.get("/completions")
def generate_completion_report(
    start_date: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
    model_type: str = Query("", description="机型筛选"),
    customer: str = Query("", description="客户筛选"),
    format: str = Query("json", description="返回格式: json 或 excel"),
    current_operator: str = Depends(get_current_operator_name),
):
    """
    完工报表（产出统计）- Completion Report (Production Output)
    基于入库历史统计产出数量，适用于产量统计和财务对账

    统计说明：
    - 统计所选时间段内产出并入库的机台数量
    - 包含所有入库方式：手动入库、配货自动入库
    - 数据来源：入库历史记录（完整、准确、可追溯）
    - 入库时间 = 机器进入库存系统的时间
    """
    import traceback
    try:
        # Validate date range
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="结束日期必须大于或等于开始日期")

        summary_df, detail_df = get_completion_output_report_data(
            start_date, end_date, model_type, customer
        )

        if summary_df.empty and detail_df.empty:
            if format == "json":
                return {"data": [], "total": 0}
            raise HTTPException(status_code=404, detail="未找到符合条件的数据")

        # Return JSON format for preview (use summary data grouped by batch)
        if format == "json":
            total_quantity = int(summary_df['数量'].sum()) if '数量' in summary_df.columns else len(detail_df)
            return {
                "data": summary_df.to_dict('records'),
                "total": total_quantity
            }

        # Return Excel format for download
        # Create a formatted sheet matching the web preview
        category_summary = calculate_category_summary(summary_df)

        # Calculate total
        total_quantity = summary_df['数量'].sum() if not summary_df.empty else 0

        # Create title row
        title_text = f"数据预览 (共 {len(summary_df)} 种机型，总产量: {total_quantity} 台)"

        # Build the combined dataframe
        rows = []

        # Add title
        rows.append([title_text, '', ''])
        rows.append(['', '', ''])  # Empty row

        # Add header
        rows.append(['机型', '数量', '占总产量百分比'])

        # Add summary data
        for _, row in summary_df.iterrows():
            rows.append([row['机型'], row['数量'], row['占比']])

        # Add total row
        rows.append(['总计', total_quantity, '100%'])

        # Add separator
        rows.append(['', '', ''])
        rows.append(['', '', ''])

        # Add category summary title
        rows.append(['机型大类汇总', '', ''])
        rows.append(['', '', ''])  # Empty row

        # Add category header
        rows.append(['机型大类', '数量', '占总产量百分比'])

        # Add category data
        for _, row in category_summary.iterrows():
            rows.append([row['机型大类'], row['数量'], row['占比']])

        # Create DataFrame
        final_df = pd.DataFrame(rows, columns=['列1', '列2', '列3'])

        sheets = {
            "完工报表": final_df,
            "明细": detail_df
        }

        return _generate_excel_response(sheets, f"完工报表_{start_date}_{end_date}")

    except HTTPException:
        raise
    except Exception as e:
        # Print full traceback for debugging
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")


@router.get("/production-ledger")
def generate_production_ledger_report(
    start_date: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
    model_type: str = Query("", description="机型筛选"),
    customer: str = Query("", description="客户筛选"),
    contract_no: str = Query("", description="合同号筛选"),
    format: str = Query("json", description="返回格式: json 或 excel"),
    current_operator: str = Depends(get_current_operator_name),
):
    """
    生产台账报表 - Production Ledger Report
    基于沙盘系统的生产完工记录，包含产线和生产时长统计

    统计说明：
    - 统计沙盘系统中生产完工的机台
    - 包含生产线、排产时间、生产时长等信息
    - 适用于生产效率分析、产线绩效统计
    - 注意：不包含直接导入的机台
    """
    try:
        # Validate date range
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="结束日期必须大于或等于开始日期")

        summary_df, detail_df = get_completion_report_data(
            start_date, end_date, model_type, customer, contract_no
        )

        if summary_df.empty and detail_df.empty:
            if format == "json":
                return {"data": [], "total": 0}
            raise HTTPException(status_code=404, detail="未找到符合条件的数据")

        # Return JSON format for preview
        if format == "json":
            return {
                "data": summary_df.to_dict('records'),
                "total": len(summary_df)
            }

        # Return Excel format for download
        sheets = {
            "汇总": summary_df,
            "明细": detail_df
        }

        return _generate_excel_response(sheets, f"生产台账报表_{start_date}_{end_date}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"报表生成失败: {str(e)}")


@router.get("/filters")
def get_report_filters():
    """
    获取报表筛选选项
    返回可用的客户、代理商、机型列表
    """
    try:
        filters = get_available_filters()
        return filters
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取筛选选项失败: {str(e)}")


@router.post("/backfill-inbound-history")
def backfill_inbound_history(
    current_operator: str = Depends(get_current_operator_name),
):
    """
    回填入库历史数据
    从 transaction_log 表中提取历史入库记录，填充到 inbound_history 表
    仅管理员可用
    """
    try:
        with get_engine().begin() as conn:
            # 查询回填前记录数
            result = conn.execute(text("SELECT COUNT(*) FROM inbound_history")).fetchone()
            before_count = result[0] if result else 0

            # 执行回填
            inserted = backfill_inbound_history_from_logs(conn)

            # 查询回填后记录数
            result = conn.execute(text("SELECT COUNT(*) FROM inbound_history")).fetchone()
            after_count = result[0] if result else 0

            # 获取统计信息
            stats = conn.execute(text("""
                SELECT
                    source AS `来源`,
                    COUNT(*) AS `记录数`,
                    MIN(DATE_FORMAT(inbound_time, '%Y-%m-%d')) AS `最早日期`,
                    MAX(DATE_FORMAT(inbound_time, '%Y-%m-%d')) AS `最晚日期`
                FROM inbound_history
                GROUP BY source
                ORDER BY COUNT(*) DESC
            """)).fetchall()

            stats_list = [
                {
                    "source": row[0],
                    "count": row[1],
                    "earliest_date": row[2],
                    "latest_date": row[3]
                }
                for row in stats
            ]

            return {
                "success": True,
                "message": "历史数据回填完成",
                "before_count": before_count,
                "after_count": after_count,
                "inserted": inserted,
                "statistics": stats_list,
                "operator": current_operator
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回填失败: {str(e)}")
