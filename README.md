# MATH MECHANICS LAB

数学パズルの「考える面白さ」を検証する、iPhoneブラウザ向け試遊研究所。

**試遊URL：** https://yamiedrich49.github.io/MATH-MECHANICS-LAB/  
**GitHub Pages設定：** https://github.com/Yamiedrich49/MATH-MECHANICS-LAB/settings/pages

## UI Build v4 — 2026-11-07

| ゲーム | 問題数 | 今回の改善 |
| --- | ---: | --- |
| SCAN GRID | 4 | スキャンと回答を**同じ1枚の盤面**で実行。候補の自動可視化を廃止し、指でマスを塗る |
| CUT CIRCUIT | 6（上級2＋旧初級4） | 数学的に全探索検証した最小切断問題（4本・5本）を先頭へ。線を横切るスワイプで切断 |
| TRIAD SHIFT | 5 | 「押した後」の答えプレビューを撤去。数字の下に対応した回転矢印を置き、約0.5秒の移動アニメーションを追加 |

### 研究上の位置づけ

この更新は**ゲーム性を評価できる状態を目指したUI・問題設計の試作**です。完成版や「面白さが証明されたゲーム」ではありません。

- SCAN GRID：行・列を調べた後、同じグリッドをドラッグで塗り、「この形で答える」
- CUT CIRCUIT：赤の電源経路だけを遮断し青の経路を残す。最初の2問は全探索で最少切断本数と一意解を確認
- TRIAD SHIFT：隣り合う3枚だけの右循環を矢印で指示し、実際の移動を目で理解する。最初の5問の最短手数は 1, 2, 4, 6, 7

Chromium（390px幅）で、SCAN GRIDの同一盤面への描画、CUT CIRCUITの上級2問のスワイプクリア、TRIAD SHIFTのアニメーション付きクリアを自動操作で検証。iPhone Safari実機と実プレイヤーの感想は未検証です。

旧版のファイルはこのリポジトリのコミット履歴から確認できます。

## GitHub Pages

リポジトリの **Settings → Pages** で、`Deploy from a branch` / `main` / `/(root)` に設定すると `index.html` を公開できます。外部ライブラリやビルド工程は不要です。
