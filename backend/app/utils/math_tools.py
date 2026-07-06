"""数学工具集成 - Sympy 等"""

import re
from typing import Any

from sympy import N, Symbol
from sympy.parsing.sympy_parser import parse_expr
from sympy.simplify.simplify import simplify


class MathTools:
    """数学工具类"""

    def verify_answer(self, student_answer: str, correct_answer: str) -> dict[str, Any]:
        """验证答案是否正确（使用 Sympy）"""
        try:
            # 清理答案（移除空格、等号等）
            student_clean = self._clean_answer(student_answer)
            correct_clean = self._clean_answer(correct_answer)

            # 尝试解析为数学表达式
            try:
                student_expr = parse_expr(student_clean)
                correct_expr = parse_expr(correct_clean)

                # 简化并比较
                diff = simplify(student_expr - correct_expr)

                # 如果差值为 0，则答案正确
                if diff == 0:
                    return {
                        "result": "correct",
                        "method": "symbolic_comparison",
                    }
                else:
                    # 尝试数值比较（可能是浮点数精度问题）
                    try:
                        num_diff = float(N(diff))
                        if abs(num_diff) < 1e-10:
                            return {
                                "result": "correct",
                                "method": "numerical_comparison",
                            }
                        else:
                            return {
                                "result": "incorrect",
                                "difference": str(diff),
                                "method": "symbolic_comparison",
                            }
                    except Exception:
                        return {
                            "result": "incorrect",
                            "difference": str(diff),
                            "method": "symbolic_comparison",
                        }
            except Exception:
                # 解析失败，使用字符串比较
                if student_clean == correct_clean:
                    return {
                        "result": "correct",
                        "method": "string_comparison",
                    }
                else:
                    return {
                        "result": "unknown",
                        "method": "string_comparison",
                        "note": "无法解析为数学表达式，使用字符串比较",
                    }
        except Exception as e:
            return {
                "result": "error",
                "error": str(e),
            }

    def _clean_answer(self, answer: str) -> str:
        """清理答案字符串"""
        # 移除空格
        cleaned = answer.strip()

        # 移除等号及其后面的内容（如果有）
        if "=" in cleaned:
            parts = cleaned.split("=", 1)
            cleaned = parts[-1].strip()

        # 移除常见的数学符号前缀
        cleaned = re.sub(r"^[xXyYzZ]\s*=\s*", "", cleaned)

        return cleaned

    def calculate(self, expression: str, variables: dict[str, float] | None = None) -> dict[str, Any]:
        """计算数学表达式"""
        try:
            expr = parse_expr(expression)

            if variables:
                # 替换变量
                for var, value in variables.items():
                    expr = expr.subs(Symbol(var), value)

            result = N(expr)

            return {
                "result": float(result),
                "expression": str(expr),
            }
        except Exception as e:
            return {
                "error": str(e),
            }

    def simplify_expression(self, expression: str) -> dict[str, Any]:
        """简化数学表达式"""
        try:
            expr = parse_expr(expression)
            simplified = simplify(expr)

            return {
                "original": expression,
                "simplified": str(simplified),
            }
        except Exception as e:
            return {
                "error": str(e),
            }
