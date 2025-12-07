import re

# テスト用の文章
test_text = "Empire of TKW (61 -> 60) -> Nerfuria (0 -> 1)"

print(f"テスト文章: {test_text}")
print("-" * 70)

# 複数のパターンをテスト
patterns = [
    (r'->\s*(.+?)\s*\(', "ユーザー提案パターン"),
    (r'\)\s*->\s*(.+?)\s*\(', "私の修正パターン"),
    (r'(?<=\))\s*->\s*(.+?)\s*\(', "後読みアサーション使用"),
    (r'\(\d+\s*->\s*\d+\)\s*->\s*(.+?)\s*\(', "数字パターン明示"),
]

for pattern, description in patterns:
    print(f"{description}: {pattern}")
    match = re.search(pattern, test_text)
    if match:
        extracted = match.group(1).strip()
        print(f"  ✅ 抽出成功: '{extracted}'")
        print(f"  マッチ全体: '{match.group(0)}'")
    else:
        print(f"  ❌ マッチしませんでした")
    print()

print("-" * 70)
print("追加テストケース:")

test_cases = [
    "Guild A (50 -> 49) -> Guild B (0 -> 1)",
    "Very Long Guild Name (100 -> 99) -> Short (5 -> 6)",
    "ABC (30 -> 29) -> XYZ Corporation (2 -> 3)",
    "Empire of TKW (61 -> 60) -> Nerfuria (0 -> 1)"
]

# 最適なパターンで全テストケースを確認
best_pattern = r'\)\s*->\s*(.+?)\s*\('
print(f"最適パターンでテスト: {best_pattern}")
for i, text in enumerate(test_cases, 1):
    match = re.search(best_pattern, text)
    if match:
        extracted = match.group(1).strip()
        print(f"{i}. '{extracted}'")
    else:
        print(f"{i}. マッチなし")