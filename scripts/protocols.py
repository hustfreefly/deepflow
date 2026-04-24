"""
轻量级协议层 - 尺度转换工具模块

提供0-1与0-100范围之间的数值转换功能。
用于将机器学习模型输出(0-1)转换为展示分数(0-100)或反之。
"""


def scale_01_to_100(value: float) -> float:
    """
    将0-1范围的值转换为0-100范围。

    Args:
        value: 0-1范围的浮点数

    Returns:
        0-100范围的浮点数 (value * 100.0)

    Note:
        输入越界时仍计算，不抛异常（调用方负责校验）
    """
    return value * 100.0


def scale_100_to_01(value: float) -> float:
    """
    将0-100范围的值转换为0-1范围。

    Args:
        value: 0-100范围的浮点数

    Returns:
        0-1范围的浮点数 (value / 100.0)

    Note:
        输入越界时仍计算，不抛异常（调用方负责校验）
    """
    return value / 100.0


def format_score(value: float, precision: int = 2) -> float:
    """
    格式化分数，处理浮点精度问题。

    Args:
        value: 原始分数值
        precision: 小数位精度，默认2位

    Returns:
        格式化后的浮点数
    """
    return round(value, precision)


# 契约测试入口
if __name__ == "__main__":
    import doctest

    doctest.testmod(verbose=True)
