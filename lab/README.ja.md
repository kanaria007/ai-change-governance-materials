# 実行モデルと結果

このディレクトリで`python -m unittest -v`を実行すると、107件のモデルテストを実行します。準備、版の照合、CI接続例は教材ルートのREADMEと書籍付録にまとめています。

## ケースの入口

| 問い | 実行・参照するもの |
|---|---|
| 証拠が古くなったときの判断 | `python run_experiments.py --output rerun-results.json` |
| E1の確認漏れと限定有効化、E2の再調査 | `python coverage_scenarios.py` |
| 探索方法を比較・選択し、別ケースに適用 | `python run_expansion.py --output rerun-expansion.json` |
| 未検証の候補が稼働版にならないこと | `python runtime_scenarios.py` |

基本モデルのケースEは、経路を確認する主張が欠けている状態です。結果キー`E_undeclared_batch_route`は、経路の存在そのものを知らないという意味ではありません。E1・E2は`expansion-results.json`の`lifecycle.rows`に分けて記録しています。

## 候補と稼働状態

`ScopedController.observe_candidate()`と互換名の`observe()`は、候補だけを更新します。`revalidate()`も稼働コードを変えません。`execute()`が現在の条件を確認し、適用に成功すると、`active_snapshot`と適用世代を更新します。

`observe_runtime()`は、稼働状態についての観測を記録する操作です。報告されたコードを読み込んだり、許可したりしません。不一致・観測不能時にはローカルの呼出しを拒否します。観測の更新には単調に増加する`epoch`が必要です。

## 変更して試すとき

探索用ソースを変えた場合は、`experiment_plan.json`にも別実験として対象を登録し直します。元の結果との比較を保つため、配布用ソースと演習用コピーを分ける方法を推奨します。

`ModuleNotFoundError`が出たら、まず作業ディレクトリが`lab/`かを確認してください。`fixture differs from declared plan`は、探索ソースと計画に記録した識別値の不一致です。

`exec()`の対象は信頼済み教材コードに限ります。未信頼のPRを隔離する環境ではありません。
