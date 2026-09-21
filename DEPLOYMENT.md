# テレアポCRM / 検索システム 本番公開手順

このアプリはPythonサーバーで動くため、GitHub Pagesだけでは公開できません。
GitHubにコードを置き、RenderなどのWebサーバーへデプロイして使います。

## Renderで公開する流れ

1. このフォルダをGitHubリポジトリへpushします。
2. Renderで `New +` → `Blueprint` を選び、GitHubリポジトリを接続します。
3. `render.yaml` が読み込まれたら、以下の環境変数をRender画面で入力します。

必須:

```text
ACCESS_USERS_JSON=発行したメールアドレスとパスワードハッシュのJSON
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

## 招待ユーザーの発行

SIGNALの管理者でログインし、イベント検索画面の「利用者管理」を開きます。

1. 招待するメールアドレスを入力します。
2. 招待を発行します。
3. 利用者は24時間有効・1回限りの招待リンクから12文字以上のパスワードを設定します。
4. 設定後は、そのメールアドレスとパスワードでログインできます。

利用者情報は同じGoogleスプレッドシートの `SIGNALユーザー` シートに保存されます。管理画面から利用停止・再開・再招待ができます。

メールを自動送信する場合はRenderへ以下を設定します。

```text
RESEND_API_KEY=ResendのAPIキー
INVITE_FROM_EMAIL=SIGNAL <invite@example.com>
APP_BASE_URL=https://signal-event-search.onrender.com
ADMIN_EMAILS=nblnetwork.000@gmail.com
```

`RESEND_API_KEY` が未設定でも招待は発行でき、管理画面に表示された招待リンクを本人へ共有できます。

既存環境から初回移行するときだけ、`ACCESS_USERS_JSON` の利用者を自動的に台帳へ取り込みます。

```json
{
  "user1@example.com": "pbkdf2_sha256$...",
  "user2@example.com": "pbkdf2_sha256$..."
}
```

未登録のメールアドレスではログインできません。利用停止すると既存セッションも次回アクセス時から無効になります。

## SIGNAL イベント検索専用版

`render.yaml` の `signal-event-search` サービスは `APP_MODE=events` で起動します。イベント検索画面だけを提供し、顧客リスト、店舗検索、求人検索、旧CRM画面とそれらのAPIは利用できません。

顧客リストは別のRenderサービスを `APP_MODE=customers` で起動します。ログイン後は `/customers.html` に移動し、イベント検索画面とイベント検索APIは利用できません。2サービスで同じ `GOOGLE_SHEET_ID` とサービスアカウントを使えば、招待利用者と個人別顧客データを引き継いだままURLだけを完全に分離できます。セッションCookieは各ドメインで別なので、それぞれのサービスでログインが必要です。

## 個人別の顧客リスト

招待された利用者は、顧客用サービスへ自分のメールアドレスでログイン後「マイ顧客リスト」で顧客を登録・確認・更新できます。データは同じGoogleスプレッドシート内の `SIGNAL顧客リスト` シートに保存され、サーバーがログイン中のメールアドレスを所有者として記録します。利用者同士のリストは分離され、管理者も画面上は自分のリストだけを見られます。スプレッドシートの編集権限を持つ人は全行を閲覧できるため、シート自体の共有範囲には注意してください。

旧CRMにブラウザー保存されていた顧客は自動移行されません。旧CRMでCSVを書き出してから、新画面で「CSVを取り込む」を使ってください。取り込み先は、その時点でログインしている本人のリストです。CSVの書き出しもできます。

## 注意

- `.env` と `service-account.json` はGitHubに上げないでください。
- Render上ではローカルのVOICEVOXアプリは動かないため、音声はブラウザ標準音声へフォールバックします。
- WhiteCUL音声を本番でも使うには、VOICEVOX Engineを別サーバーで常時起動して `VOICEVOX_URL` に設定する必要があります。
- OpenAI APIはChatGPTの契約とは別に、OpenAI Platform側のBilling設定が必要です。
