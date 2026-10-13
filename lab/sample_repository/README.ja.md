# E2用のサンプルソース

`document_routes.py`は、モジュール直下の五つの入口を持つ信頼済み教材です。`@entrypoint`、`permitted`、`emit_document`は`route_discovery.probe()`が実行時に与えます。単体のWebアプリや実ジョブの設定ではありません。

名前と外部出力の探索は、このソースを実際に構文解析します。`scheduled_delivery`のテナント比較欠落は意図した故障です。教材から外部へ情報を送信する処理はありません。
