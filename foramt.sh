#!/bin/bash

# 设置要格式化的文件扩展名
FILE_EXTENSIONS=("*.cpp" "*.hpp" "*.h" "*.c" "*.cc")
SHELL_FILE_EXTENSIONS=("*.sh")

# 格式化 C++ 文件
for ext in "${FILE_EXTENSIONS[@]}"; do
	find . -type f -name "$ext" | while read -r file; do
		echo "$(realpath "$file")"
		clang-format -i "$file"
	done
done

# 格式化 Shell 文件
for ext in "${SHELL_FILE_EXTENSIONS[@]}"; do
	find . -type f -name "$ext" | while read -r file; do
		echo "$(realpath "$file")"
		shfmt -w "$file"
	done
done

echo "All files have been formatted."
