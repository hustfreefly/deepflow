"""
Protocols模块契约测试

验证protocols.py模块符合cage/protocols.yaml契约规范。
"""

import unittest
import sys
from pathlib import Path

# 添加项目根目录到路径
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "cage"))

from protocols import scale_01_to_100, scale_100_to_01, format_score


class TestScale01To100(unittest.TestCase):
    """测试scale_01_to_100函数"""

    def test_zero_returns_zero(self):
        """0.0应该返回0.0"""
        self.assertEqual(scale_01_to_100(0.0), 0.0)

    def test_one_returns_hundred(self):
        """1.0应该返回100.0"""
        self.assertEqual(scale_01_to_100(1.0), 100.0)

    def test_half_returns_fifty(self):
        """0.5应该返回50.0"""
        self.assertEqual(scale_01_to_100(0.5), 50.0)

    def test_quarter_returns_twenty_five(self):
        """0.25应该返回25.0"""
        self.assertEqual(scale_01_to_100(0.25), 25.0)

    def test_negative_input_computes(self):
        """负值输入仍计算，不抛异常（边界测试）"""
        result = scale_01_to_100(-0.5)
        self.assertEqual(result, -50.0)

    def test_overflow_input_computes(self):
        """>1输入仍计算，不抛异常（边界测试）"""
        result = scale_01_to_100(1.5)
        self.assertEqual(result, 150.0)


class TestScale100To01(unittest.TestCase):
    """测试scale_100_to_01函数"""

    def test_zero_returns_zero(self):
        """0.0应该返回0.0"""
        self.assertEqual(scale_100_to_01(0.0), 0.0)

    def test_hundred_returns_one(self):
        """100.0应该返回1.0"""
        self.assertEqual(scale_100_to_01(100.0), 1.0)

    def test_fifty_returns_half(self):
        """50.0应该返回0.5"""
        self.assertEqual(scale_100_to_01(50.0), 0.5)

    def test_twenty_five_returns_quarter(self):
        """25.0应该返回0.25"""
        self.assertEqual(scale_100_to_01(25.0), 0.25)

    def test_negative_input_computes(self):
        """负值输入仍计算，不抛异常（边界测试）"""
        result = scale_100_to_01(-50.0)
        self.assertEqual(result, -0.5)

    def test_overflow_input_computes(self):
        """>100输入仍计算，不抛异常（边界测试）"""
        result = scale_100_to_01(150.0)
        self.assertEqual(result, 1.5)


class TestRoundTrip(unittest.TestCase):
    """测试双向转换的一致性"""

    def test_round_trip_preserves_value(self):
        """0-1范围值往返转换应保持近似相等"""
        original = 0.75
        converted = scale_01_to_100(original)
        back = scale_100_to_01(converted)
        self.assertAlmostEqual(original, back, places=10)

    def test_round_trip_100_to_01_to_100(self):
        """0-100范围值往返转换应保持近似相等"""
        original = 75.0
        converted = scale_100_to_01(original)
        back = scale_01_to_100(converted)
        self.assertAlmostEqual(original, back, places=10)


class TestFormatScore(unittest.TestCase):
    """测试format_score函数"""

    def test_default_precision(self):
        """默认精度为2位小数"""
        result = format_score(3.14159)
        self.assertEqual(result, 3.14)

    def test_custom_precision(self):
        """自定义精度"""
        result = format_score(3.14159, precision=4)
        self.assertEqual(result, 3.1416)

    def test_zero_precision(self):
        """0位精度"""
        result = format_score(3.7, precision=0)
        self.assertEqual(result, 4.0)


class TestContractCompliance(unittest.TestCase):
    """测试契约合规性"""

    def test_module_has_all_interface_methods(self):
        """模块应包含契约中定义的所有接口方法"""
        import protocols as p
        self.assertTrue(hasattr(p, 'scale_01_to_100'))
        self.assertTrue(hasattr(p, 'scale_100_to_01'))
        self.assertTrue(callable(getattr(p, 'scale_01_to_100')))
        self.assertTrue(callable(getattr(p, 'scale_100_to_01')))


if __name__ == "__main__":
    unittest.main(verbosity=2)
