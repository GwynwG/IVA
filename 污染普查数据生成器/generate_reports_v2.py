import random
import os
from datetime import datetime, timedelta
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

# 给定的辐射超标地面点位ID列表
POINT_IDS = [
    55, 56, 57, 58, 85, 86, 87, 88, 115, 116, 117, 118,
    145, 146, 147, 148, 175, 176, 177, 178, 205, 206, 207, 208,
    235, 236, 237, 238, 265, 266, 267, 268, 295, 296, 297, 298,
    325, 326, 327, 328, 355, 356, 357, 358, 385, 386, 387, 388,
    415, 416, 417
]

def generate_random_date(year=2025):
    """生成2025年内的随机日期"""
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31)
    days_diff = (end_date - start_date).days
    random_days = random.randint(0, days_diff)
    random_date = start_date + timedelta(days=random_days)
    return random_date

def generate_random_time():
    """生成随机时间（小时、分钟、秒）"""
    hour = random.randint(0, 23)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return hour, minute, second

def format_timedelta(td):
    """将timedelta格式化为'X小时Y分钟Z秒'"""
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours}小时{minutes}分钟{seconds}秒"

def generate_report(template_path, output_dir, report_num):
    """生成单个报告文件"""
    # 加载模板文档
    doc = Document(template_path)
    
    # 获取表格（第一个表格）
    table = doc.tables[0]
    
    # 生成随机日期
    random_date = generate_random_date(2025)
    
    # 生成开始时间和结束时间（同一天）
    start_hour, start_minute, start_second = generate_random_time()
    end_hour, end_minute, end_second = generate_random_time()
    
    # 确保结束时间晚于开始时间
    start_time = datetime(random_date.year, random_date.month, random_date.day, 
                         start_hour, start_minute, start_second)
    end_time = datetime(random_date.year, random_date.month, random_date.day, 
                       end_hour, end_minute, end_second)
    
    if end_time <= start_time:
        # 如果结束时间不晚于开始时间，将结束时间设置为开始时间后1-4小时
        hours_to_add = random.randint(1, 4)
        end_time = start_time + timedelta(hours=hours_to_add)
    
    # 计算任务历时时长
    duration = end_time - start_time
    
    # 格式化时间字符串
    start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
    duration_str = format_timedelta(duration)
    
    # 随机选择辐射超标地面点位ID（2-20个）
    num_points = random.randint(2, 20)
    selected_ids = random.sample(POINT_IDS, num_points)
    
    # 修改表格内容
    # 行索引（0-based）:
    # 0: 标题行
    # 1: 任务开始时间
    # 2: 任务结束时间
    # 3: 任务历时时长
    # 4: 探测地面网格数
    # 5: 辐射超标地面网格个数
    # 6: 探测手套孔数
    # 7: 辐射超标手套孔个数
    # 8: 辐射超标地面点位ID标题行
    # 9-11: 现有的3个辐射超标地面点位ID行（将被替换）
    # 12: 辐射超标手套孔名称标题行
    # 13: 手套孔1#
    # 14: 手套孔2#
    # 15: …（省略号）
    
    # 修改任务开始时间（行1，列1）
    table.cell(1, 1).text = start_time_str
    
    # 修改任务结束时间（行2，列1）
    table.cell(2, 1).text = end_time_str
    
    # 修改任务历时时长（行3，列1）
    table.cell(3, 1).text = duration_str
    
    # 修改辐射超标地面网格个数（行5，列1）
    table.cell(5, 1).text = str(num_points)
    
    # 处理辐射超标地面点位ID行
    # 首先，确定需要删除的行（行9-11）
    # 我们需要删除这些行，然后插入新行
    # 但要注意行索引会变化
    
    # 获取表格总行数
    total_rows = len(table.rows)
    
    # 删除现有的辐射超标地面点位ID行（行9-11）
    # 由于删除行后索引会变化，我们从最后一行开始删除
    rows_to_delete = [9, 10, 11]
    # 确保这些行存在
    rows_to_delete = [r for r in rows_to_delete if r < total_rows]
    # 按降序排序，以便从后往前删除
    for row_idx in sorted(rows_to_delete, reverse=True):
        # 删除行
        table._tbl.remove(table.rows[row_idx]._tr)
    
    # 现在表格行数减少了，我们需要在正确位置插入新行
    # 插入位置：在"辐射超标地面点位ID"标题行之后（原行8，现在仍然是行8）
    # 在手套孔标题行之前（原行12，现在可能是9，因为删除了3行）
    
    # 重新计算手套孔标题行的位置
    # 原行12现在应该是 12 - 3 = 9（如果删除了3行）
    glove_title_row_idx = 9  # 调整后的索引
    
    # 为每个选中的ID插入新行
    for i, point_id in enumerate(selected_ids):
        # 在手套孔标题行之前插入新行
        new_row_idx = glove_title_row_idx + i
        # 插入行（复制标题行的格式）
        new_row = table.add_row()
        # 移动新行到正确位置
        # 由于add_row总是在末尾添加，我们需要移动它
        # 我们将新行插入到手套孔标题行之前
        # 获取新行的XML元素
        new_tr = new_row._tr
        # 获取手套孔标题行的XML元素
        glove_tr = table.rows[glove_title_row_idx]._tr
        # 将新行插入到手套孔标题行之前
        glove_tr.getparent().insertbefore(new_tr, glove_tr)
        
        # 设置新行的内容
        # 第一列：点位ID
        new_row.cells[0].text = str(point_id)
        # 第二列：测量值（保持0.12）
        new_row.cells[1].text = "0.12"
    
    # 手套孔部分保持不变（行索引已调整）
    # 保存文档
    output_filename = f"普查报告_{report_num:03d}.docx"
    output_path = os.path.join(output_dir, output_filename)
    doc.save(output_path)
    
    return output_path, start_time_str, end_time_str, duration_str, selected_ids

def main():
    # 路径配置
    template_path = r"C:\Users\罗兆东\Desktop\4XTS\AI高价值场景应用\污染普查数据可视化\示例文件\20250701.docx"
    output_dir = r"C:\Users\罗兆东\dist\污染普查数据生成器\生成报告"
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 生成50个报告
    print("开始生成50个污染普查报告...")
    for i in range(1, 51):
        try:
            output_path, start_time, end_time, duration, selected_ids = generate_report(
                template_path, output_dir, i
            )
            print(f"生成报告 {i:02d}: {os.path.basename(output_path)}")
            print(f"  开始时间: {start_time}")
            print(f"  结束时间: {end_time}")
            print(f"  历时: {duration}")
            print(f"  辐射超标点位ID: {selected_ids}")
            print()
        except Exception as e:
            print(f"生成报告 {i:02d} 时出错: {e}")
    
    print(f"报告生成完成！共生成50个文件，保存在: {output_dir}")

if __name__ == "__main__":
    main()