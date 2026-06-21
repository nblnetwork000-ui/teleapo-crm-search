# テレアポCRM / 検索システム 本番公開手順

このアプリはPythonサーバーで動くため、GitHub Pagesだけでは公開できません。
GitHubにコードを置き、RenderなどのWebサーバーへデプロイして使います。

## Renderで公開する流れ

1. このフォルダをGitHubリポジトリへpushします。
2. Renderで `New +` → `Blueprint` を選び、GitHubリポジトリを接続します。
3. `render.yaml` が読み込まれたら、以下の環境変数をRender画面で入力します。

必須:

```text
ACCESS_MEMBER_ID=ログイン用ID
ACCESS_PASSWORD=ログイン用パスワード
YAHOO_CLIENT_ID=YahooローカルサーチAPIのClient ID
GOOGLE_SHEET_ID=追記先スプレッドシートID
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=GoogleサービスアカウントJSONのBase64
```

任意:

```text
OPENAI_API_KEY=OpenAI APIキー
OPENAI_MODEL=gpt-5
```

4. デプロイ完了後、RenderのURLの `/login` を開きます。
5. スマホ・タブレット・別PCでも同じURLでログインできます。

## 注意

- `.env` と `service-account.json` はGitHubに上げないでください。
- Render上ではローカルのVOICEVOXアプリは動かないため、音声はブラウザ標準音声へフォールバックします。
- WhiteCUL音声を本番でも使うには、VOICEVOX Engineを別サーバーで常時起動して `VOICEVOX_URL` に設定する必要があります。
- OpenAI APIはChatGPTの契約とは別に、OpenAI Platform側のBilling設定が必要です。
