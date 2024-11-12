import os
import csv
import xml.etree.ElementTree as ET
from pathlib import Path


# 创建测试数据目录
def create_test_data_structure():
    base_dir = Path("test_data")
    base_dir.mkdir(exist_ok=True)

    # 创建option目录
    option_dir = base_dir / "option"
    option_dir.mkdir(exist_ok=True)

    # 创建rmb.csv文件
    create_rmb_csv(base_dir / "rmb.csv")

    # 创建option目录下的CSV文件
    create_option_csvs(option_dir)


def create_rmb_csv(file_path):
    """创建rmb.csv测试数据"""
    data = [
        ["source", "translation"],
        ["1 RMB", "1 元"],
        ["2 RMB", "2 元"],
        ["10 RMB", "10 元"],
        ["100 RMB", "100 元"],
        ["1000 RMB", "1000 元"],
        ["Credit Card", "信用卡"],
        ["Debit Card", "借记卡"],
        ["Cash", "现金"],
        ["Payment Method", "支付方式"],
        ["Balance", "余额"],
    ]

    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(data)


def create_option_csvs(directory):
    """创建option目录下的多个CSV文件"""
    # 系统选项
    system_options = [
        ["source", "translation"],
        ["Settings", "设置"],
        ["Language", "语言"],
        ["Display", "显示"],
        ["Sound", "声音"],
        ["Network", "网络"],
        ["About", "关于"],
    ]

    # 用户选项
    user_options = [
        ["source", "translation"],
        ["Profile", "个人资料"],
        ["Username", "用户名"],
        ["Password", "密码"],
        ["Email", "电子邮件"],
        ["Phone", "电话"],
        ["Address", "地址"],
    ]

    # 产品选项
    product_options = [
        ["source", "translation"],
        ["Category", "类别"],
        ["Price", "价格"],
        ["Quantity", "数量"],
        ["Stock", "库存"],
        ["Discount", "折扣"],
        ["Description", "描述"],
    ]

    # 写入文件
    files = {
        "system_options.csv": system_options,
        "user_options.csv": user_options,
        "product_options.csv": product_options,
    }

    for filename, data in files.items():
        with open(directory / filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(data)


if __name__ == "__main__":
    create_test_data_structure()
