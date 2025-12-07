import re

# 修正後の正規表現パターン（正しい版）
pattern = r'\)\s*->\s*([^(]+?)\s*\('

# テスト用の文章
test_text = "Empire of TKW (61 -> 60) -> Nerfuria (0 -> 1)"

print(f"テスト文章: {test_text}")
print(f"正規表現パターン: {pattern}")
print("-" * 50)

# パターンマッチを実行
match = re.search(pattern, test_text)

if match:
    extracted_guild = match.group(1).strip()
    print(f"✅ 抽出成功!")
    print(f"抽出されたギルド名: '{extracted_guild}'")
    print(f"マッチした全体: '{match.group(0)}'")
else:
    print("❌ マッチしませんでした")

print("-" * 50)

# 他のパターンもテスト
test_cases = [
    "Guild A (50 -> 49) -> Guild B (0 -> 1)",
    "Very Long Guild Name (100 -> 99) -> Short (5 -> 6)",
    "ABC (30 -> 29) -> XYZ Corporation (2 -> 3)",
    "Empire of TKW (61 -> 60) -> Nerfuria (0 -> 1)"
]

print("追加テストケース:")
for i, text in enumerate(test_cases, 1):
    match = re.search(pattern, text)
    if match:
        extracted = match.group(1).strip()
        print(f"{i}. '{text}' -> '{extracted}'")
    else:
        print(f"{i}. '{text}' -> マッチなし")