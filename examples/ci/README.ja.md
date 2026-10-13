# GitHub・CI接続例

第8章の「何を検査した結果か」を残す例です。教材モデルの107件のテストを実行し、チェックアウトしたリビジョン、入力ファイルのSHA-256、Python、コマンド、結果とログを記録します。業務要求の充足判定や本番操作の許可は行いません。

## ローカルで動かす

教材をGitリポジトリのルートに配置し、追跡対象をコミットして、未変更の状態にします。そのルートから実行します。

```bash
python examples/ci/collect_lab_result.py --output ci-results
```

GitとPythonが必要です。`ci-results/ci-result.json`と`ci-results/unittest.log`が出力されます。`ci-results/`はGitの追跡対象から外します。`GITHUB_SHA`が設定されている場合は、実際の`HEAD`との一致も確認します。

記録スクリプトの判定処理には、教材モデルとは別に8件のテストがあります。

```bash
python -m unittest discover -s examples/ci -v
```

本書の制作時には、ローカルのGitリポジトリで107件成功の記録を作成し、イベントのリビジョンが違う場合と追跡対象に未コミットの変更がある場合の拒否を確認しました。

## GitHub Actionsの定義例

`.github/workflows/lab-checks.yml`にワークフローを配置済みです。GitHubでリポジトリを公開し、Actionsが有効な環境では対象イベントによって実行されます。GitHub上での初回実行とartifactのアップロードは未検証です。

`pull_request`、`merge_group`、mainへのpushを入口にし、チェックアウトした対象を記録します。`contents: read`とし、本番用秘密情報やデプロイ権限を渡さない例です。

Actionsの参照先は2026年10月13日に公式リポジトリで確認した次のコミットです。

| Action | バージョン | 固定したコミット |
|---|---|---|
| checkout | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| setup-python | v7.0.0 | `5fda3b95a4ea91299a34e894583c3862153e4b97` |
| upload-artifact | v7.0.1 | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` |

SHAへの固定は、指定したコードを識別するためのものです。これだけでActionの安全性を保証したり、将来の更新確認を不要にしたりするものではありません。

## 信頼境界

PRと同じリポジトリのコードが作るJSONは、PRと同じ信頼範囲にあります。自己申告の`PASS`を、そのまま特権付きジョブの実行許可にしないでください。実行基盤、ワークフロー、対象リビジョン、成果物の由来を保護された判断経路で照合する設計が別途必要です。

この例は、未信頼コードを本番権限で実行する`pull_request_target`や`workflow_run`の代替として使うものではありません。完成済みのSLSA attestationや、本番用Admission Controllerでもありません。

## 公式資料

- [GitHub Docs: Managing a merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)
- [GitHub Docs: Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)
- [checkoutの固定コミット](https://github.com/actions/checkout/commit/3d3c42e5aac5ba805825da76410c181273ba90b1)
- [setup-pythonの固定コミット](https://github.com/actions/setup-python/commit/5fda3b95a4ea91299a34e894583c3862153e4b97)
- [upload-artifactの固定コミット](https://github.com/actions/upload-artifact/commit/043fb46d1a93c77aae656e7c1c64a875d1fc6a0a)

## 公開用リポジトリに同梱している検査

ワークフローは教材の収録内容を`verify_package.py`で照合し、CI記録スクリプト8件・パッケージ検査13件のテストを別途実行してから、教材本体107件のテスト結果を記録します。これらは別集計であり、CIは本番への変更を許可しません。
