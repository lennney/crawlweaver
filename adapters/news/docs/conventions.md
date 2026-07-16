# Conventions

> 编码规范。新增文件时阅读。

## 命名
- 类: PascalCase
- 函数/变量: snake_case
- 文件: snake_case.py
- 常量: UPPER_SNAKE_CASE

## 导入顺序
1. 标准库
2. 第三方库
3. 项目内部模块
（每组空行分隔）

## 类型注解
- 所有公共函数必须有类型注解
- 私有函数建议有
- 禁止使用 `Any`（用具体类型或 TypeVar）
