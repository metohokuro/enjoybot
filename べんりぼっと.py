import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View  # ここでButtonとViewをインポート
import os
import requests
import random
import datetime
import asyncio
import aiohttp
import textwrap
import traceback
import aiofiles
import json
import psutil
import platform
import time
import yt_dlp as youtube_dl  
CHANNELS_FILE = 'channels.txt'

number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


role_message_map = {}


# Botの設定
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True  # メンバー情報の取得に必要
intents.message_content = True
intents.reactions = True
intents.guild_messages = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

SECRET_PASSWORD = 'ぱすわーど' #基本的なパスワード
WEBHOOK_URL = "うぇぶふっく" #botが入ったときに送信するウェブフック
BOT_INVITE_LINK = "しょうたい" #botの招待リンク
SUPPORT_SERVER_URL = 'さぽーと'
ADMIN_PASSWORD = "ぱすわーど"  # giveawayの履歴を送信するパスワード
LOG_CHANNEL_ID = 12345  # sayのlogチャンネル
ALLOWED_USERS = {12345}  # unban_allを使える人のユーザーID
OWNER_ID = 12345  # !give_allと!commandを使える人のユーザーID
TOKEN = 'とーくん' # botのトークン

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
            print('いいよ')
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

@bot.tree.command(name="say", description="指定されたユーザー風のメッセージを送信します")
@app_commands.describe(user="メッセージを送信する際のユーザー", message="送信するメッセージ内容")
async def say(interaction: discord.Interaction, user: discord.Member, message: str):
    """
    指定されたチャンネルにWebhookを作成して送信するが、
    メッセージにロールメンション（@everyone, @here含む）が含まれていた場合は送信を中止し、
    みんなに「○○が△△のロールを使おうとしました！」と通知する。
    """
    try:
        # 実行者の情報
        executor = interaction.user
        guild = interaction.guild  # ギルド情報を取得

        # ログ用チャンネルを取得
        log_channel = bot.get_channel(LOG_CHANNEL_ID)

        # 🛑 @everyone や @here の検出
        if "@everyone" in message or "@here" in message or '@認証済み' in message or '@認証まだ' in message or '@member' in message:
            warning_message = f"⚠️ {executor.mention} が everyone または here を使おうとしました！"
            log_message = f"🛑 `/say` コマンドで everyone または here のメンションが検出されました。\n\n"
            log_message += f"👤 実行者: {executor.mention} ({executor.name} / ID: {executor.id})"

            # ログ用チャンネルに警告を送信
            if log_channel:
                await log_channel.send(log_message)

            # 実行者にエラーメッセージを送信
            await interaction.response.send_message("⚠️ everyone または here を含むメッセージは送信できません！", ephemeral=True)
            return

        # 🛑 通常のロールメンションの検出
        mentioned_roles = [role for role in guild.roles if f"<@&{role.id}>" in message]
        if mentioned_roles:
            role_names = ", ".join([role.mention for role in mentioned_roles])  # メンション形式
            role_plain_names = ", ".join([role.name for role in mentioned_roles])  # 文字列形式

            warning_message = f"⚠️ {executor.mention} が {role_names} を使おうとしました！"
            log_message = f"🛑 `/say` コマンドでロールメンションが検出されました。\n\n"
            log_message += f"👤 実行者: {executor.mention} ({executor.name} / ID: {executor.id})\n"
            log_message += f"📝 試みたロール: {role_plain_names}"

            # ログ用チャンネルに警告を送信
            if log_channel:
                await log_channel.send(log_message)

            # 実行者にエラーメッセージを送信
            await interaction.response.send_message("⚠️ ロールメンションを含むメッセージは送信できません！", ephemeral=True)
            return

        # 実行されたチャンネル
        channel = interaction.channel

        # Webhookを作成
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

        # 実行者のみに通知
        await interaction.response.send_message("メッセージを送信しました！", ephemeral=True)

        # `/say` コマンドの実行ログを送信
        if log_channel:
            executor_info = (
                f"👤 実行者: {executor.mention}\n"
                f"📝 名前: {executor.display_name}\n"
                f"🔗 ユーザー名: {executor.name}\n"
                f"🆔 ID: {executor.id}"
                f"📝 内容: {message}"
            )
            await log_channel.send(f"🛠 `/say` コマンドが実行されました！\n\n{executor_info}")

    except Exception as e:
        # エラー発生時に、まだ `interaction.response.send_message()` が実行されていなければ送信
        if not interaction.response.is_done():
            await interaction.response.send_message(f"エラーが発生しました: {str(e)}", ephemeral=True)
        else:
            # すでにレスポンス済みの場合、ログチャンネルにエラー情報を送信
            if log_channel:
                await log_channel.send(f"⚠️ エラーが発生しました: {str(e)}")
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
    print(景品)
    print('だめだよ！')
    
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


#def is_admin(interaction: discord.Interaction) -> bool:
#    return interaction.user.guild_permissions.administrator
#
#async def send_dm(member: discord.Member, embed: discord.Embed, queue: asyncio.Queue):
#    """ メンバーにDMを送信し、結果をqueueに追加する（並列処理用） """
#    if not member.bot:
#        try:
#            await member.send(embed=embed)
#            await queue.put(("success", member))
#        except discord.Forbidden:
#            await queue.put(("fail", member))
#
#@bot.tree.command(name="news", description="サーバーの全メンバーにニュースをDMで送信します（管理者限定）")
#@app_commands.describe(title="ニュースのタイトル", description="ニュースの説明")
#async def news(interaction: discord.Interaction, title: str, description: str):
#   if not interaction.user.guild_permissions.administrator:
#       await interaction.response.send_message("❌ あなたはこのコマンドを実行する権限がありません。", ephemeral=True)
#        return
#
#    guild = interaction.guild
#    if not guild:
#        await interaction.response.send_message("サーバー内でのみ使用可能です。", ephemeral=True)
#        return
#
#    embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
#    embed.set_footer(text=f"送信元: {guild.name}")
#
#   response_message = await interaction.response.send_message("⌛ ニュースの送信を開始しています...\n✅ 送信成功: 0人\n❌ 送信失敗: 0人", ephemeral=False)
#
#   queue = asyncio.Queue()
#    tasks = []
#
#    for member in guild.members:
#        tasks.append(send_dm(member, embed, queue))
#
#    # 並列処理で全員にDMを送る（同時に50人程度を処理）
#    CHUNK_SIZE = 50  # 一度に並列処理する数
#    sent_count = 0
#    failed_count = 0
#
#    # 進捗表示用のタスク
#    async def update_progress():
#        nonlocal sent_count, failed_count
#        while True:
#            try:
#                result, _ = await queue.get()
#                if result == "success":
#                    sent_count += 1
#                else:
#                    failed_count += 1
#                if sent_count + failed_count == len(tasks):
#                    break
#                #await response_message.edit(content=f"⌛ ニュースの送信中...\n✅ 送信成功: {sent_count}人\n❌ 送信失敗: {failed_count}人")
#            except:
#                break
#
#    progress_task = asyncio.create_task(update_progress())
#
#    # 50人ずつ並列処理
#    for i in range(0, len(tasks), CHUNK_SIZE):
#        await asyncio.gather(*tasks[i:i + CHUNK_SIZE])
#
#    await progress_task  # 進捗更新タスクを終了
#
#    # 最終結果を表示
#    await response_message.edit(content=f"✅ **ニュースの送信が完了しました！**\n✅ 送信成功: {sent_count}人\n❌ 送信失敗: {failed_count}人")

class RoleButton(discord.ui.View):
    def __init__(self, role: discord.Role):
        super().__init__(timeout=None)
        self.role = role

    @discord.ui.button(label="ロールを付与", style=discord.ButtonStyle.green)
    async def give_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.role in interaction.user.roles:
            await interaction.response.send_message("すでにこのロールを持っています。", ephemeral=True)
        else:
            try:
                await interaction.user.add_roles(self.role)
                await interaction.response.send_message(f"{self.role.name} を付与しました！", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("エラー: Botにロールを付与する権限がありません。管理者に問い合わせてください。", ephemeral=True)


@bot.tree.command(name="addrole", description="指定したロールの付与ボタンを作成します（管理者のみ実行可能）")
@app_commands.describe(role="付与するロールを指定してください")
@app_commands.checks.has_permissions(administrator=True)
async def addrole(interaction: discord.Interaction, role: discord.Role):
    embed = discord.Embed(title="ロール付与", description=f"以下のボタンを押すと `{role.name}` ロールが付与されます。", color=discord.Color.blue())
    view = RoleButton(role)
    await interaction.response.send_message(embed=embed, view=view)

@addrole.error
async def addrole_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("このコマンドは管理者のみ実行可能です。", ephemeral=True)


# 管理者チェックのための非同期関数
# 管理者チェックのための非同期関数
async def is_admin(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator

# Bot招待リンク
# BOT_INVITE_LINK = "https://discord.com/oauth2/authorize?client_id=1338863781849337856&permissions=690148027510&integration_type=0&scope=bot+applications.commands"

# /renameコマンド
@bot.tree.command(name="実績数反映")
@app_commands.describe(
    prefix="名前の前に追加するオプション(例:👑実績)",
    additional_number="追加の実績があればここに数字を入力"
)
async def 実績数反映(interaction: discord.Interaction, prefix: str = '', additional_number: int = 0):
    """
    コマンドを実行したチャンネルの名前を変更します。オプションで追加の数字を指定できます。
    メッセージ数に追加の数字を加算した結果が新しいチャンネル名に設定されます。
    """
    if not await is_admin(interaction):  # is_adminを非同期で呼び出し
        await interaction.response.send_message("このコマンドを実行する権限がありません。", ephemeral=True)
        return
    await interaction.response.defer()  # まずインタラクションを確認して応答を遅延させる
    # 実行したチャンネルを取得
    channel = interaction.channel
    
    # チャンネル内のメッセージ数をカウント
    message_count = 0
    async for _ in channel.history(limit=None):
        message_count += 1
    
    # メッセージ数に追加の数字を加算
    total_count = message_count + additional_number
    
    # 新しいチャンネル名を作成
    new_name = f"{prefix}-{total_count}" if prefix else f"{channel.name}-{total_count}"
    await channel.edit(name=new_name)

    # Embedメッセージ作成
    embed = discord.Embed(
        title="実績数変更",
        description=f"チャンネル名が「{new_name}」に変更されました。",
        color=discord.Color.green()
    )

    # ボタン作成
    button = Button(label="Botを招待", style=discord.ButtonStyle.link, url=BOT_INVITE_LINK)
    
    # Viewにボタンを追加
    view = View()
    view.add_item(button)

    # 最初にインタラクションのレスポンスを送信（エラー回避）
    

    # 変更結果をEmbed形式で送信
    await interaction.followup.send(embed=embed, view=view)  # followupで追加レスポンスを送る


@bot.tree.command(name="help", description="Botの機能一覧を表示")
@app_commands.describe(private="True: 自分だけ / False: みんなに見える")
async def help_command(interaction: discord.Interaction, private: bool = True):
    embed = discord.Embed(
        title="📜 Botの機能一覧",
        description="以下のコマンドが使用できます。",
        color=discord.Color.blue()
    )
    embed.add_field(name="🎟️ /ticket", value="チケットを作成するボタンを作る", inline=False)
    embed.add_field(name="🗣️ /say", value="Webhookを使って他人になりすませる", inline=False)
    embed.add_field(name="📢 /announce", value="**[管理者専用]** Botを導入しているサーバーのオーナーのDMにお知らせを飛ばす", inline=False)
    embed.add_field(name="📜 /server", value="**[管理者専用]** Botを導入しているサーバーの情報を管理者のDMに送る", inline=False)
    embed.add_field(name="🔢 /message_count", value="メッセージ数を数える", inline=False)
    embed.add_field(name="🎁 /giveaway", value="抽選を行い、当選者にDMを送る", inline=False)
    embed.add_field(name="🛠️ /develop", value="**[管理者専用]** giveawayの履歴を管理者のDMに送信", inline=False)
    embed.add_field(name="📦 /senddm", value="指定したユーザーのDMに商品を配達する", inline=False)
    embed.add_field(name="🛡️ /addrole", value="指定したロールを付与するembedを設置する", inline=False)
    embed.add_field(name="📊 /実績数反映", value="実行したチャンネルのメッセージ数を読み取って名前を変更する", inline=False)
    embed.add_field(name="💾 /save", value="実行したチャンネルをtxt形式で抽出する", inline=False)
    embed.set_footer(text="※このメッセージは自分にしか見えません")

    visibility_text = "（このメッセージは自分にしか見えません）" if private else ""
    embed.set_footer(text=f"※ /help private: False で全員に表示できます {visibility_text}")

    await interaction.response.send_message(embed=embed, ephemeral=private)

ERROR_LOG_DIR = "error_logs"
os.makedirs(ERROR_LOG_DIR, exist_ok=True)

# ✅ エラー報告モーダル
class ErrorModal(discord.ui.Modal, title="エラー報告"):
    def __init__(self, ログチャンネル):
        super().__init__()
        self.ログチャンネル = ログチャンネル

    エラー内容 = discord.ui.TextInput(label="エラー内容を入力", placeholder="発生した問題を詳しく書いてください", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        log_embed = discord.Embed(title="エラー報告", color=discord.Color.red())
        log_embed.add_field(name="報告者", value=interaction.user.mention, inline=False)
        log_embed.add_field(name="内容", value=self.エラー内容.value, inline=False)
        # ✅ エラー内容を `txt` ファイルに保存
        filename = f"{ERROR_LOG_DIR}/error_report_{interaction.user.id}.txt"
        with open(filename, "w", encoding="utf-8") as file:
            file.write(self.エラー内容.value)

        # ✅ ログチャンネルに送信
        await self.ログチャンネル.send(embed=log_embed)

        await interaction.response.send_message("エラー報告が送信されました！", ephemeral=True)

# ✅ 「購入」「エラー」ボタン
# ✅ 購入ボタンの View
class PurchaseView(discord.ui.View):
    def __init__(self, 商品名, 価格, ログチャンネル, vouch):
        super().__init__(timeout=None)
        self.persisted = True  # 🔹 再起動後も有効にする
        self.商品名 = 商品名
        self.価格 = 価格
        self.ログチャンネル = ログチャンネル
        self.vouch = vouch

    @discord.ui.button(label="購入", style=discord.ButtonStyle.green)
    async def purchase(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PurchaseModal(self.商品名, self.価格, self.ログチャンネル, self.vouch))

    @discord.ui.button(label="エラー", style=discord.ButtonStyle.danger)
    async def error(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ErrorModal(self.ログチャンネル))

# ✅ キャンセル用モーダル
class CancelOrderModal(discord.ui.Modal, title="キャンセル理由を入力"):
    def __init__(self, user, 商品名, 購入サーバー, log_message, admin):
        super().__init__()
        self.user = user
        self.商品名 = 商品名
        self.購入サーバー = 購入サーバー
        self.log_message = log_message
        self.admin = admin  # 誰が実行したか

    reason = discord.ui.TextInput(label="キャンセル理由を入力", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        # ✅ DMにキャンセル通知（Embed）
        embed = discord.Embed(title="購入がキャンセルされました", color=discord.Color.red())
        embed.add_field(name="商品名", value=self.商品名, inline=False)
        embed.add_field(name="理由", value=self.reason.value, inline=False)
        embed.add_field(name="購入したサーバー", value=self.購入サーバー, inline=False)

        await self.user.send(embed=embed)
        await interaction.response.send_message("キャンセルしました！", ephemeral=True)

        # ✅ ログのメッセージを編集（ボタンを無効化）
        new_embed = self.log_message.embeds[0]
        new_embed.title = f"{self.admin.display_name} が商品をキャンセルしました"
        await self.log_message.edit(embed=new_embed, view=None)  # ボタン無効化

# ✅ 購入モーダル
class PurchaseModal(discord.ui.Modal, title="購入数を入力"):
    数量 = discord.ui.TextInput(label="個数を入力", placeholder="例: 2", required=True)

    def __init__(self, 商品名, 価格, ログチャンネル, vouch):
        super().__init__()
        self.商品名 = 商品名
        self.価格 = 価格
        self.ログチャンネル = ログチャンネル
        self.vouch = vouch

    async def on_submit(self, interaction: discord.Interaction):
        数量 = int(self.数量.value)
        合計金額 = 数量 * self.価格
        view = ConfirmPurchaseView(self.商品名, 数量, 合計金額, self.ログチャンネル, self.vouch)
        await interaction.response.send_message(f"**{合計金額}円です！**", view=view, ephemeral=True)

# ✅ 購入確定ボタン
class ConfirmPurchaseView(discord.ui.View):
    def __init__(self, 商品名, 数量, 合計金額, ログチャンネル, vouch):
        super().__init__()
        self.商品名 = 商品名
        self.数量 = 数量
        self.合計金額 = 合計金額
        self.ログチャンネル = ログチャンネル
        self.vouch = vouch

    @discord.ui.button(label="購入確定", style=discord.ButtonStyle.primary)
    async def confirm_purchase(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ✅ サーバー名 (サーバーID) を渡す
        購入サーバー = f"{interaction.guild.name} ({interaction.guild.id})"
        await interaction.response.send_modal(PaymentModal(
            self.商品名, self.数量, self.合計金額, 購入サーバー,
            self.ログチャンネル, self.vouch
        ))

# ✅ 支払い情報モーダル
class PaymentModal(discord.ui.Modal, title="支払い情報を入力"):
    paypay_link = discord.ui.TextInput(label="PayPayリンクを入力", placeholder="https://paypay... ", required=True)
    password = discord.ui.TextInput(label="パスワード(任意)", required=False)

    def __init__(self, 商品名, 数量, 合計金額, 購入サーバー,ログチャンネル, vouch):
        super().__init__()
        self.商品名 = 商品名
        self.数量 = 数量
        self.合計金額 = 合計金額
        self.ログチャンネル = ログチャンネル
        self.vouch = vouch
        self.購入サーバー = 購入サーバー

    async def on_submit(self, interaction: discord.Interaction):
        log_embed = discord.Embed(title="購入リクエスト", color=discord.Color.orange())
        log_embed.add_field(name="商品名", value=self.商品名, inline=False)
        log_embed.add_field(name="個数", value=str(self.数量), inline=False)
        log_embed.add_field(name="金額", value=f"{self.合計金額}円", inline=False)
        log_embed.add_field(name="PayPayリンク", value=self.paypay_link.value, inline=False)
        log_embed.add_field(name="パスワード", value=self.password.value if self.password.value else "None", inline=False)
        log_embed.add_field(name="購入者", value=interaction.user.mention, inline=False)

        log_message = await self.ログチャンネル.send(embed=log_embed)
        await log_message.edit(view=SendView(interaction.user, self.商品名, self.数量, self.合計金額, self.ログチャンネル, self.購入サーバー, self.vouch, log_message))

        await interaction.response.send_message("管理者が対応するまでお待ち下さい！", ephemeral=True)

# ✅ 「送信」「キャンセル」ボタン（管理者用）
class SendView(discord.ui.View):
    def __init__(self, user, 商品名, 数量, 合計金額, ログチャンネル, 購入サーバー, vouch, log_message):
        super().__init__(timeout=None)
        self.persisted = True  # 🔹 再起動後も有効にする
        self.user = user
        self.商品名 = 商品名
        self.数量 = 数量
        self.合計金額 = 合計金額
        self.ログチャンネル = ログチャンネル
        self.vouch = vouch
        self.log_message = log_message
        self.購入サーバー = 購入サーバー

    @discord.ui.button(label="送信", style=discord.ButtonStyle.success)
    async def send(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SendProductModal(self.user, self.商品名,self.数量,self.合計金額, self.購入サーバー,self.ログチャンネル,self.vouch, self.log_message, interaction.user))

    @discord.ui.button(label="理由をつけてキャンセル", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CancelOrderModal(self.user, self.商品名, self.購入サーバー, self.log_message, interaction.user))

# ✅ 商品送信モーダル（ファイル保存＆ログ）
class SendProductModal(discord.ui.Modal, title="購入者に送信"):
    content = discord.ui.TextInput(label="送信内容を入力", required=True)

    def __init__(self, user, 商品名, 数量, 合計金額, 購入サーバー, ログチャンネル, vouch, log_message, admin):
        super().__init__()
        self.user = user
        self.商品名 = 商品名
        self.数量 = 数量
        self.合計金額 = 合計金額
        self.購入サーバー = 購入サーバー  # ✅ サーバーID込み
        self.ログチャンネル = ログチャンネル
        self.vouch = vouch
        self.log_message = log_message
        self.admin = admin




    content = discord.ui.TextInput(label="送信内容を入力", style=discord.TextStyle.paragraph,required=True)
    

    async def on_submit(self, interaction: discord.Interaction):
        filename = f"{self.商品名}.txt"
        with open(filename, "w") as file:
            file.write(
                f"商品: {self.商品名}\n"
                f"個数: {self.数量}\n"
                f"金額: {self.合計金額}円\n"
                f"購入サーバー: {self.購入サーバー}\n"  # ✅ サーバー名 (ID) を記録
                f"内容:\n{self.content.value}"
                )
        # ✅ DMに商品を送信（Embed）
        dm_embed = discord.Embed(title="ご購入ありがとうございます！", color=discord.Color.green())
        dm_embed.add_field(name="商品名", value=self.商品名, inline=False)
        dm_embed.add_field(name="内容", value=self.content.value, inline=False)
        dm_embed.add_field(name="購入したサーバー", value=self.購入サーバー, inline=False)  # ✅ 修正
        with open(filename, "rb") as file:
            await self.user.send(embed=dm_embed, file=discord.File(file, filename))

        #await self.user.send(embed=embed)
        await interaction.response.send_message("送信しました！", ephemeral=True)

        # ✅ vouchチャンネルに実績を送信（Embed）
        vouch_embed = discord.Embed(title="購入実績", color=discord.Color.blue())
        vouch_embed.add_field(name="商品名", value=self.商品名, inline=False)
        vouch_embed.add_field(name="金額", value=f"{self.合計金額}円", inline=False)
        vouch_embed.add_field(name="個数", value=str(self.数量), inline=False)
        vouch_embed.add_field(name="購入者", value=self.user.mention, inline=False)
        await self.vouch.send(embed=vouch_embed)

        # ✅ ログチャンネルに送信完了を通知（Embed）
        #log_embed = discord.Embed(title=f"{self.admin.display_name} が商品を送信しました", color=discord.Color.green())
        #log_embed.add_field(name="商品名", value=self.商品名, inline=False)
        #log_embed.add_field(name="個数", value=str(self.数量), inline=False)
        #log_embed.add_field(name="金額", value=f"{self.合計金額}円", inline=False)
        #log_embed.add_field(name="送信者", value=self.admin.mention, inline=False)
        #await self.ログチャンネル.send(embed=log_embed)
         # ✅ ログチャンネルに txt ファイルを添付
        #filename = f"{self.商品名}.txt"
        

        # ✅ ログのメッセージを編集（ボタンを無効化）
        new_embed = self.log_message.embeds[0]
        new_embed.title = f"{self.admin.display_name} が商品を送信しました"
        with open(filename, "rb") as file:
            await self.log_message.edit(embed=new_embed, view=None)  # ボタンを無効化
            await self.ログチャンネル.send(file=discord.File(file, filename))
        

        await interaction.response.send_message("送信完了しました！", ephemeral=True)
# ✅ パネル作成コマンド（管理者のみ）
@bot.tree.command(name="panel", description="自販機パネルを作成")
@app_commands.check(is_admin)
async def panel(interaction: discord.Interaction, 商品名: str, 説明: str, 価格: int, ログチャンネル: discord.TextChannel, vouch: discord.TextChannel):
    embed = discord.Embed(title=商品名, description=説明, color=discord.Color.blue())
    embed.add_field(name="価格", value=f"{価格}円", inline=False)
    print('あああ')
    view = PurchaseView(商品名, 価格, ログチャンネル, vouch)
    await interaction.response.send_message(embed=embed, view=view)
    print('おおお')
@panel.error
async def panel_error(interaction: discord.Interaction, error):
    if isinstance(error, commands.MissingPermissions):
        await interaction.response.send_message("⚠ **このコマンドは管理者のみ実行できます！**", ephemeral=True)



class VouchModal(discord.ui.Modal, title="実績を記入"):
    def __init__(self, user: discord.Member, target_channel: discord.TextChannel):
        super().__init__()
        self.user = user
        self.target_channel = target_channel

        self.product = discord.ui.TextInput(label="商品名", placeholder="例: ノートPC", required=True)
        self.quantity = discord.ui.TextInput(label="個数", placeholder="例: 1", required=True)
        self.price = discord.ui.TextInput(label="金額(円)", placeholder="例: 50000", required=True)
        self.review = discord.ui.TextInput(label="感想", style=discord.TextStyle.paragraph, required=True)
        self.rating = discord.ui.TextInput(label="評価 (1~5)", placeholder="例: 5", required=True)

        self.add_item(self.product)
        self.add_item(self.quantity)
        self.add_item(self.price)
        self.add_item(self.review)
        self.add_item(self.rating)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title="📌 実績", color=discord.Color.green())
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="商品", value=self.product.value, inline=False)
        embed.add_field(name="個数", value=self.quantity.value, inline=True)
        embed.add_field(name="金額", value=f"{self.price.value} 円", inline=True)
        embed.add_field(name="感想", value=self.review.value, inline=False)
        embed.add_field(name="評価", value=f"{self.rating.value}/5", inline=True)
        embed.add_field(name="記入者", value=interaction.user.mention, inline=True)
        embed.add_field(name="対応スタッフ", value=self.user.mention, inline=True)

        invite_button = discord.ui.Button(label="📩 Botを招待", url=BOT_INVITE_LINK)

        view = discord.ui.View()
        view.add_item(invite_button)

        await self.target_channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ 実績が送信されました！", ephemeral=True)

class VouchButton(discord.ui.View):
    def __init__(self, user: discord.Member, target_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.persisted = True  # 🔹 再起動後も有効にする
        self.user = user
        self.target_channel = target_channel

    @discord.ui.button(label="📝 実績を記入", style=discord.ButtonStyle.primary)
    async def vouch_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user == self.user:
            await interaction.response.send_modal(VouchModal(user=self.user, target_channel=self.target_channel))
        else:
            await interaction.response.send_message("❌ このボタンは作成者のみ使用できます！", ephemeral=True)

@bot.tree.command(name="vouch", description="実績を記入するボタンを表示します")
@app_commands.describe(channel="実績を送信するチャンネル")
async def vouch(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ このコマンドは管理者のみ実行できます！", ephemeral=True)
        return

    view = VouchButton(user=interaction.user, target_channel=channel)
    await interaction.response.send_message("📌 実績を記入するにはボタンを押してください！", view=view, ephemeral=True)

async def get_chat_history(channel: discord.TextChannel):
    """ 指定チャンネルのチャット履歴を取得し、テキストとして返す """
    messages = [msg async for msg in channel.history(limit=1000)]  # 修正！
    chat_log = f"📜 {channel.name} のチャット履歴\n\n"

    for msg in reversed(messages):  # 古いメッセージ順にする
        chat_log += f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author}: {msg.content}\n"

    return chat_log

class VouchModal2(discord.ui.Modal, title="実績を記入"):
    def __init__(self, user: discord.Member, target_channel: discord.TextChannel, delete_channel: discord.TextChannel):
        super().__init__()
        self.user = user
        self.target_channel = target_channel
        self.delete_channel = delete_channel

        self.product = discord.ui.TextInput(label="商品名", placeholder="例: ノートPC", required=True)
        self.quantity = discord.ui.TextInput(label="個数", placeholder="例: 1", required=True)
        self.price = discord.ui.TextInput(label="金額(円)", placeholder="例: 50000", required=True)
        self.review = discord.ui.TextInput(label="感想", style=discord.TextStyle.paragraph, required=True)
        self.rating = discord.ui.TextInput(label="評価 (1~5)", placeholder="例: 5", required=True)

        self.add_item(self.product)
        self.add_item(self.quantity)
        self.add_item(self.price)
        self.add_item(self.review)
        self.add_item(self.rating)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title="📌 実績", color=discord.Color.green())
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="商品", value=self.product.value, inline=False)
        embed.add_field(name="個数", value=self.quantity.value, inline=True)
        embed.add_field(name="金額", value=f"{self.price.value} 円", inline=True)
        embed.add_field(name="感想", value=self.review.value, inline=False)
        embed.add_field(name="評価", value=f"{self.rating.value}/5", inline=True)
        embed.add_field(name="記入者", value=interaction.user.mention, inline=True)
        embed.add_field(name="対応スタッフ", value=self.user.mention, inline=True)

        invite_button = discord.ui.Button(label="📩 Botを招待", url=BOT_INVITE_LINK)

        view = discord.ui.View()
        view.add_item(invite_button)

        await self.target_channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ 実績が送信されました！", ephemeral=True)

        # 実績記入後、チャンネル履歴を取得・送信・削除
        await delete_channel_history(self.delete_channel, interaction.user)

class VouchButton2(discord.ui.View):
    def __init__(self, user: discord.Member, target_channel: discord.TextChannel, delete_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.persisted = True  # 🔹 再起動後も有効にする
        self.user = user
        self.target_channel = target_channel
        self.delete_channel = delete_channel

    @discord.ui.button(label="📝 実績を記入", style=discord.ButtonStyle.primary)
    async def vouch_button2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VouchModal2(user=self.user, target_channel=self.target_channel, delete_channel=self.delete_channel))

async def delete_channel_history(channel: discord.TextChannel, executed_user: discord.Member):
    """ チャンネルの履歴を保存し、オーナー・実行者・記入者に送信した後、チャンネルを削除 """
    chat_log = await get_chat_history(channel)
    guild_owner = channel.guild.owner

    # 🔹 `flatten()` を削除し、async for を使う
    first_message = [msg async for msg in channel.history(limit=1)]
    record_author = first_message[0].author if first_message else None

    dm_recipients = [guild_owner, executed_user, record_author] if record_author else [guild_owner, executed_user]

    for recipient in dm_recipients:
        try:
            # 🔹 recipient が BOT の場合はスキップ
            if recipient is None or recipient.bot:
                continue

            # 🔹 DM チャンネルがない場合は作成
            if recipient.dm_channel is None:
                await recipient.create_dm()

            await recipient.send(f"📜 {channel.name} のチャット履歴:\n```{chat_log}```")
        except discord.Forbidden:
            print(f"⚠️ {recipient} にDMを送れませんでした")

    await channel.delete()
@bot.tree.command(name="vouch_delete", description="実績を記入し、チャンネルを削除します")
@app_commands.describe(channel="実績を送信するチャンネル", delete_channel="削除するチャンネル")
async def vouch_delete(interaction: discord.Interaction, channel: discord.TextChannel, delete_channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ このコマンドは管理者のみ実行できます！", ephemeral=True)
        return

    view = VouchButton2(user=interaction.user, target_channel=channel, delete_channel=delete_channel)
    await interaction.response.send_message("📌 実績を記入するにはボタンを押してください！", view=view, ephemeral=True)

@bot.tree.command(name="nuke", description="現在のチャンネルを削除し、同じ設定で再作成します")
async def nuke(ctx: discord.Interaction):
    # ユーザーがチャンネル管理の権限を持っているか確認
    if not ctx.user.guild_permissions.manage_channels:
        await ctx.response.send_message("❌ このコマンドを実行する権限がありません。", ephemeral=True)
        return

    channel = ctx.channel  # 実行したチャンネル
    guild = ctx.guild  # サーバー情報を取得
    owner = guild.owner  # サーバーオーナー

    # チャンネルの情報を保存
    overwrites = channel.overwrites
    category = channel.category
    name = channel.name
    position = channel.position

    # 📌 確認メッセージ
    await ctx.response.send_message("⚠️ このチャンネルを削除して再作成しますか？（10秒以内に ✅ を押してください）", ephemeral=True)
    msg = await ctx.original_response()
    await msg.add_reaction("✅")

    def check(reaction, user):
        return user == ctx.user and str(reaction.emoji) == "✅"

    try:
        await bot.wait_for("reaction_add", timeout=10.0, check=check)
    except:
        await msg.edit(content="⏳ 時間切れ。キャンセルしました。")
        return

    # 📝 メッセージ履歴を保存
    file_name = f"{channel.name}_history.txt"
    async with aiofiles.open(file_name, "w", encoding="utf-8") as file:
        async for message in channel.history(limit=None, oldest_first=True):
            await file.write(f"[{message.created_at}] {message.author}: {message.content}\n")

    # 📤 DMで履歴ファイルを送信
    async def send_dm(user):
        if user:
            try:
                with open(file_name, "rb") as file:
                    await user.send(f"🔹 {channel.name} の履歴ファイルです。", file=discord.File(file, file_name))
            except Exception as e:
                print(f"⚠️ {user} へのDM送信失敗: {e}")

    await send_dm(ctx.user)  # 実行者に送信
    await send_dm(owner)  # サーバーオーナーに送信

    # 🔥 チャンネルを削除
    await channel.delete()

    # 🔄 新しいチャンネルを作成
    new_channel = await guild.create_text_channel(name, category=category, overwrites=overwrites)
    await new_channel.edit(position=position)

    # 📤 新しいチャンネルに履歴を送信
    try:
        with open(file_name, "rb") as file:
            await new_channel.send(f"📂 過去のメッセージ履歴:", file=discord.File(file, file_name))
    except Exception as e:
        print(f"⚠️ 新しいチャンネルへの履歴送信失敗: {e}")

    # 🔄 ファイル削除（不要になったら削除）

    # 📌 「このボットを招待する」ボタン
    class InviteButton(discord.ui.View):
        def __init__(self):
            super().__init__()
            self.add_item(discord.ui.Button(label="このボットを招待する", url=BOT_INVITE_LINK, style=discord.ButtonStyle.link))

    # ✅ 作成完了メッセージ + ボタン
    await new_channel.send(
        f"✅ {ctx.user.mention} によってチャンネルがリセットされました！",
        view=InviteButton()
    )

# データ保存用ファイル
DATA_FILE = "lucky.json"

# データを読み込む関数
def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# データを書き込む関数
def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# スロット機能
@bot.tree.command(name="slot", description="スロットを回して777を狙おう！")
async def slot(interaction: discord.Interaction):
    await interaction.response.defer()  # 実行の遅延（演出のため）

    # 最初のメッセージ（プレースホルダー）
    embed = discord.Embed(title="🎰 スロットマシン 🎰", description="回転中…", color=discord.Color.gold())
    message = await interaction.followup.send(embed=embed, wait=True)

    # スロットの回転アニメーション
    spinning = ["｜🎰｜🎰｜🎰｜", "｜🔄｜🔄｜🔄｜", "｜💫｜💫｜💫｜"]
    for spin in spinning:
        embed.description = spin
        await message.edit(embed=embed)
        await asyncio.sleep(1)  # 1秒ずつ待機

    # スロットの結果を決定
    numbers = [random.randint(1, 9) for _ in range(3)]
    result = f"｜{numbers[0]}｜{numbers[1]}｜{numbers[2]}｜"

    embed.description = result

    if numbers == [7, 7, 7]:  # 777が出た場合
        user = interaction.user.name
        data = load_data()
        data[user] = data.get(user, 0) + 1  # 回数を記録
        save_data(data)

        rank = sum(data.values())  # 何人目の豪運者か
        embed.add_field(
            name="🎉 豪運！",
            value=f"おめでとう！あなたは **{rank}人目** の豪運の持ち主です！！",
            inline=False,
        )
        embed.color = discord.Color.green()

    await message.edit(embed=embed)

# ランキング機能（上位5位まで表示）
@bot.tree.command(name="leaderboard", description="歴代の豪運ランキング（上位5位）を表示")
async def leaderboard(interaction: discord.Interaction):
    data = load_data()
    sorted_data = sorted(data.items(), key=lambda x: x[1], reverse=True)

    embed = discord.Embed(title="🏆 豪運ランキング（上位5名） 🏆", color=discord.Color.blue())
    if sorted_data:
        for i, (user, count) in enumerate(sorted_data[:5], start=1):  # 上位5位まで表示
            medal = ["🥇", "🥈", "🥉", "🏅", "🎖"][i - 1]  # 1~5位までのアイコン
            embed.add_field(name=f"{medal} #{i} {user}", value=f"🎰 {count}回", inline=False)
    else:
        embed.add_field(name="まだ誰も777を出していません！", value="最初の豪運者になろう！")

    await interaction.response.send_message(embed=embed)

GUILD_ID = 1096651765681750056
# データ保存フォルダ
DATA_FOLDER = "data"
if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)

# 🟢 定型文を保存する関数
def save_template(name, title, description, author):
    filepath = os.path.join(DATA_FOLDER, f"{name}.json")
    data = {"title": title, "description": description, "author": author}
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# 🔵 定型文を読み込む関数
def load_template(name):
    filepath = os.path.join(DATA_FOLDER, f"{name}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

# 🟣 定型文一覧を取得する関数
def get_template_list():
    return [f.split(".json")[0] for f in os.listdir(DATA_FOLDER) if f.endswith(".json")]

# 🟡 定型文を削除する関数
def delete_template(name):
    filepath = os.path.join(DATA_FOLDER, f"{name}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
        return True
    return False

# 🛑 コマンドを実行できるか確認する関数
def check_owner(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        raise app_commands.CheckFailure("このコマンドはBotのオーナーしか使えません。")

# 📌 「/定型文追加」コマンド
@bot.tree.command(name="定型文追加", description="定型文を追加します")
@app_commands.describe(name="定型文の名前", title="Embedのタイトル", description="Embedの説明")
async def add_template(interaction: discord.Interaction, name: str, title: str, description: str):
    check_owner(interaction)  # 👈 実行者チェック
    author = interaction.user.name
    filepath = os.path.join(DATA_FOLDER, f"{name}.json")
    data = {"title": title, "description": description, "author": author}
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    await interaction.response.send_message(f"✅ 定型文 **{name}** を追加しました！", ephemeral=True)

# 📌 他のコマンドも同じようにチェックを追加
@bot.tree.command(name="定型文", description="定型文をEmbedで表示します")
async def show_template(interaction: discord.Interaction):
    check_owner(interaction)  # 👈 実行者チェック
    templates = [f.split(".json")[0] for f in os.listdir(DATA_FOLDER) if f.endswith(".json")]
    if not templates:
        await interaction.response.send_message("⚠️ 登録されている定型文がありません。", ephemeral=True)
        return

    class TemplateSelect(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=30)
            options = [discord.SelectOption(label=t) for t in templates]
            self.select = discord.ui.Select(placeholder="表示する定型文を選択", options=options)
            self.select.callback = self.select_callback
            self.add_item(self.select)

        async def select_callback(self, select_interaction: discord.Interaction):
            template = json.load(open(os.path.join(DATA_FOLDER, f"{self.select.values[0]}.json"), "r", encoding="utf-8"))
            embed = discord.Embed(title=template["title"], description=template["description"], color=discord.Color.blue())
            embed.set_footer(text=f"作成者: {template['author']}")
            await select_interaction.response.send_message(embed=embed)

    await interaction.response.send_message(view=TemplateSelect(), ephemeral=True)

# 📌 「/定型文編集」コマンド（選択メニュー＋テキスト入力）
@bot.tree.command(name="定型文編集", description="定型文を編集します")
@commands.has_permissions(administrator=True)
async def edit_template(interaction: discord.Interaction):
    templates = get_template_list()
    if not templates:
        await interaction.response.send_message("⚠️ 編集できる定型文がありません。", ephemeral=True)
        return
    
    class EditSelect(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=30)
            options = [discord.SelectOption(label=t) for t in templates]
            self.select = discord.ui.Select(placeholder="編集する定型文を選択", options=options)
            self.select.callback = self.select_callback
            self.add_item(self.select)

        async def select_callback(self, select_interaction: discord.Interaction):
            template_name = self.select.values[0]
            template = load_template(template_name)

            class EditModal(discord.ui.Modal, title="定型文編集"):
                new_name = discord.ui.TextInput(label="新しい名前", default=template_name)
                new_title = discord.ui.TextInput(label="新しいタイトル", default=template["title"])
                new_description = discord.ui.TextInput(label="新しい説明", default=template["description"], style=discord.TextStyle.long)

                async def on_submit(self, modal_interaction: discord.Interaction):
                    save_template(self.new_name.value, self.new_title.value, self.new_description.value, template["author"])
                    if self.new_name.value != template_name:
                        delete_template(template_name)
                    await modal_interaction.response.send_message(f"✅ 定型文 **{self.new_name.value}** を更新しました！", ephemeral=True)

            await select_interaction.response.send_modal(EditModal())

    await interaction.response.send_message(view=EditSelect(), ephemeral=True)

# 📌 「/定型文削除」コマンド
@bot.tree.command(name="定型文削除", description="定型文を削除します")
async def delete_template_command(interaction: discord.Interaction):
    check_owner(interaction)  # 👈 実行者チェック
    templates = [f.split(".json")[0] for f in os.listdir(DATA_FOLDER) if f.endswith(".json")]
    if not templates:
        await interaction.response.send_message("⚠️ 削除できる定型文がありません。", ephemeral=True)
        return

    class DeleteSelect(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=30)
            options = [discord.SelectOption(label=t) for t in templates]
            self.select = discord.ui.Select(placeholder="削除する定型文を選択", options=options)
            self.select.callback = self.select_callback
            self.add_item(self.select)

        async def select_callback(self, select_interaction: discord.Interaction):
            name = self.select.values[0]
            os.remove(os.path.join(DATA_FOLDER, f"{name}.json"))
            await select_interaction.response.send_message(f"🗑️ 定型文 **{name}** を削除しました！", ephemeral=True)

    await interaction.response.send_message(view=DeleteSelect(), ephemeral=True)

@bot.tree.command(name="bot_info", description="BOTの情報を表示")
async def bot_info(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    # システム情報の取得
    cpu_usage = psutil.cpu_percent(interval=1)
    memory_usage = psutil.virtual_memory().percent
    python_version = platform.python_version()
    discord_version = discord.__version__

    # Pingの取得
    start_time = time.time()
    #await interaction.response.defer()  # 応答遅延（オプション）
    end_time = time.time()
    ping = round((end_time - start_time) * 1000, 2)

    # ボタンの作成（招待リンク & サポートサーバー）
    invite_button = discord.ui.Button(label="🤖 BOTを招待", url=BOT_INVITE_LINK)
    support_button = discord.ui.Button(label="🛠 サポートサーバー", url=SUPPORT_SERVER_URL)

    # Embedの作成
    embed = discord.Embed(title="🤖 BOT情報", color=discord.Color.blue())
    embed.add_field(name="🖥️ CPU使用率", value=f"{cpu_usage}%", inline=True)
    embed.add_field(name="📊 メモリ使用率", value=f"{memory_usage}%", inline=True)
    embed.add_field(name="🐍 Python", value=f"{python_version}", inline=True)
    embed.add_field(name="📦 discord.py", value=f"{discord_version}", inline=True)
    embed.add_field(name="🏓 Ping", value=f"{ping}ms", inline=True)
    embed.add_field(name="👤 制作者", value="<@1096650724387078156> (@metohokuro)", inline=False)

    # Viewにボタンを追加
    view = discord.ui.View()
    view.add_item(invite_button)
    view.add_item(support_button)

    # メッセージ送信
    await interaction.followup.send(embed=embed, view=view)

# 曲リストをギルドごとに持つ
queue = {}
loop_enabled = {}  # ギルドごとのループ状態

async def play_next(interaction: discord.Interaction):
    guild_id = interaction.guild.id

    if not queue[guild_id]:
        await interaction.followup.send("✅ プレイリストの再生が完了しました！")
        return

    next_video_url = queue[guild_id].pop(0)

    ydl_opts = {'format': 'bestaudio/best', 'quiet': True}
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(next_video_url, download=False)
        audio_url = info['url']
        title = info.get('title', 'Unknown Title')
        video_id = info.get('id')
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

    vc = interaction.guild.voice_client
    vc.play(discord.FFmpegPCMAudio(audio_url),
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next(interaction), bot.loop))

    # ループがONだったら再度キューに追加
    if loop_enabled.get(guild_id, False):
        queue[guild_id].append(next_video_url)

    embed = discord.Embed(title="🎶 再生中", description=title, color=discord.Color.green())
    embed.set_thumbnail(url=thumbnail_url)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="play", description="YouTubeの音楽を再生します")
@app_commands.describe(url="再生したいYouTubeのURL（プレイリストもOK）")
async def play(interaction: discord.Interaction, url: str):
    await interaction.response.defer()

    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("ボイスチャンネルに入ってからコマンドを使ってね！", ephemeral=True)
        return

    channel = interaction.user.voice.channel

    if not interaction.guild.voice_client:
        await channel.connect()
    elif interaction.guild.voice_client.channel != channel:
        await interaction.guild.voice_client.move_to(channel)

    try:
        ydl_opts = {
            'extract_flat': 'in_playlist',
            'quiet': True,
        }
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        guild_id = interaction.guild.id
        queue[guild_id] = []

        if 'entries' in info:
            # プレイリスト
            for entry in info['entries']:
                queue[guild_id].append(f"https://www.youtube.com/watch?v={entry['id']}")
        else:
            queue[guild_id].append(url)

        await play_next(interaction)

    except Exception as e:
        await interaction.followup.send(f"エラーが発生しました: {e}")

@bot.tree.command(name="skip", description="今の曲をスキップします")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await interaction.response.send_message("⏭ スキップしました！", ephemeral=True)
    else:
        await interaction.response.send_message("今は何も再生していないよ！", ephemeral=True)

@bot.tree.command(name="loop", description="再生リストをループします（ON/OFF）")
async def loop(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    current = loop_enabled.get(guild_id, False)
    loop_enabled[guild_id] = not current
    status = "🔁 ループON！" if not current else "⏹ ループOFF！"
    await interaction.response.send_message(status)

@bot.tree.command(name="stop", description="音楽を停止します")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await interaction.response.send_message("⏹️ 音楽を停止しました。")
    else:
        await interaction.response.send_message("今は何も再生していないよ。")

@bot.tree.command(name="leave", description="ボイスチャンネルから切断します")
async def leave(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        await interaction.response.send_message("👋 切断しました。")
    else:
        await interaction.response.send_message("まだボイスチャンネルにいないよ。")


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    bot.add_view(SendView())  # 🔹 Bot起動時にボタンを登録
    bot.add_view(PurchaseView())  # 🔹 Bot起動時にボタンを登録
    bot.add_view(VouchButton())  # 🔹 Bot起動時にボタンを登録
    bot.add_view(VouchButton2())  # 🔹 Bot起動時にボタンを登録

@bot.tree.command(name="save", description="このチャンネルのメッセージを保存して送信します")
@app_commands.describe(public="チャンネルにも送るかどうか（true: 送る, false: 送らない）")
async def save(interaction: discord.Interaction, public: bool):
    await interaction.response.defer(thinking=True)  # 応答遅延でタイムアウト回避
    
    channel = interaction.channel
    guild = interaction.guild
    owner = guild.owner if guild else None  # サーバーオーナーを取得
    messages = []
    
    async for message in channel.history(limit=100):  # 最新100件のメッセージを取得
        messages.append(f"[{message.author.display_name}] {message.content}")
    
    log_content = "\n".join(reversed(messages))
    filename = f"{channel.name}_log.txt"
    
    with open(filename, "w", encoding="utf-8") as file:
        file.write(log_content)
    
    # DM用のファイルを開く
    with open(filename, "rb") as file:
        discord_file = discord.File(file, filename=filename)
        await interaction.user.send(file=discord_file, content=f"チャンネル {channel.mention} のログです。")
    
    if public:
        # チャンネル用のファイルを開き直す
        with open(filename, "rb") as file:
            discord_file_public = discord.File(file, filename=filename)
            await channel.send(file=discord_file_public, content=f"{interaction.user.mention} がこのチャンネルのログを保存しました。")
    
    # サーバーオーナーにもDMを送信
    if owner:
        with open(filename, "rb") as file:
            discord_file_owner = discord.File(file, filename=filename)
            await owner.send(file=discord_file_owner, content=f"{interaction.user.mention} がチャンネル {channel.mention} をセーブしました！")
    
    await interaction.followup.send("メッセージの保存が完了しました。", ephemeral=True)


def clean_code(code):
    """コードブロックを削除し、言語指定 (python など) を取り除く"""
    if code.startswith("```") and code.endswith("```"):
        lines = code.split("\n")
        if lines[0].startswith("```") and len(lines) > 1:
            lines.pop(0)  # 最初の「```python」などを削除
        if lines[-1].startswith("```"):
            lines.pop(-1)  # 最後の「```」を削除
        return "\n".join(lines).strip()  # 余計な空白や改行を削除
    return code.strip()

@bot.command(name="command")
async def execute(ctx, *, code: str):
    """!command でPythonコードを実行"""
    if ctx.author.id != OWNER_ID:
        await ctx.reply("このコマンドを実行する権限がありません。")
        return

    code = clean_code(code)  # コードブロックを削除
    local_vars = {"ctx": ctx}  # ctx を local に追加

    # 実行開始: メッセージに 🔄 リアクションをつける
    await ctx.message.add_reaction("🔄")

    try:
        # コードを非同期関数にラップする
        exec(
            f"async def __ex(ctx):\n{textwrap.indent(code, '    ')}",
            globals(),
            local_vars
        )

        # 定義した関数を実行
        await local_vars["__ex"](ctx)

        # 完了後、✅リアクションをつける
        await ctx.message.clear_reactions()
        await ctx.message.add_reaction("✅")

    except Exception as e:
        # エラーハンドリング
        error_message = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        
        # Embedでエラーメッセージを表示
        embed = discord.Embed(title="エラーが発生しました", description=f"```py\n{error_message}\n```", color=discord.Color.red())
        await ctx.message.clear_reactions()
        await ctx.message.add_reaction("❌")
        await ctx.send(embed=embed)  # エラーメッセージを送信


# チャンネルIDを保存する関数
def save_channel_id(channel_id):
    with open(CHANNELS_FILE, 'a') as file:
        file.write(f"{channel_id}\n")

# チャンネルIDを削除する関数
def remove_channel_id(channel_id):
    try:
        with open(CHANNELS_FILE, 'r') as file:
            lines = file.readlines()
        with open(CHANNELS_FILE, 'w') as file:
            for line in lines:
                if line.strip() != str(channel_id):
                    file.write(line)
    except FileNotFoundError:
        pass

# チャンネルIDを読み込む関数
def load_channel_ids():
    try:
        with open(CHANNELS_FILE, 'r') as file:
            return [int(line.strip()) for line in file.readlines()]
    except FileNotFoundError:
        return []

# イベント: ボットが起動したとき
@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')

# イベント: メッセージが送信されたとき
@bot.event
async def on_message(message):

    # 保存されたチャンネルIDのリストを取得
    channel_ids = load_channel_ids()
    
    # メッセージが保存されたチャンネルIDに一致する場合、👍リアクションを追加
    if message.channel.id in channel_ids:
        await message.add_reaction('👍')

    # 他のコマンドも正しく動作させるためにon_message内で処理を行う
    await bot.process_commands(message)

# コマンド: チャンネルIDを追加する（管理者のみ実行可能）
@bot.command(name='addreaction')
@commands.has_permissions(manage_channels=True)
async def addreaction(ctx):
    channel_id = ctx.channel.id
    channel_ids = load_channel_ids()

    if channel_id in channel_ids:
        await ctx.send("すでに追加されてます！")
    else:
        save_channel_id(channel_id)
        await ctx.send(f"このチャンネル({ctx.channel.name})のメッセージに自動でリアクションをつけるように設定しました！")

# コマンド: チャンネルIDを削除する（管理者のみ実行可能）
@bot.command(name='deletereaction')
@commands.has_permissions(manage_channels=True)
async def deletereaction(ctx):
    channel_id = ctx.channel.id
    channel_ids = load_channel_ids()

    if channel_id not in channel_ids:
        await ctx.send("このチャンネルはまだ追加されていません！")
    else:
        remove_channel_id(channel_id)
        await ctx.send(f"このチャンネル({ctx.channel.name})のメッセージに対するリアクション設定を削除しました。")
        
@bot.command()
async def give_role(ctx, guild_id: int, user_id: int, role_name: str):
    # サーバーIDを指定して、そのサーバーを取得
    guild = bot.get_guild(guild_id)
    
    if ctx.author.id != OWNER_ID:
        await ctx.send("このコマンドは管理者のみ実行できます。")
        return
    
    if guild is None:
        await ctx.send("指定されたサーバーが見つかりません。Botがそのサーバーに参加しているか確認してください。")
        return
    

    # 指定されたIDを元にユーザーを取得
    user = guild.get_member(user_id)
    if user is None:
        await ctx.send("指定されたユーザーが見つかりません。")
        return

    # ロールを指定
    role = discord.utils.get(guild.roles, name=role_name)
    if role is None:
        await ctx.send("指定されたロールが見つかりません。")
        return

    # ロールをユーザーに付与
    try:
        await user.add_roles(role)
        await ctx.send(f"{user.mention} にロール '{role_name}' を付与しました。")
    except discord.Forbidden:
        await ctx.send("ロールの付与に失敗しました。権限を確認してください。")
@bot.command()
@commands.has_permissions(ban_members=True)
async def unban_all(ctx, server_id: int):
    """
    指定したユーザーのみが実行可能な、指定サーバーのBANを全解除するコマンド
    """
    # 実行者の確認
    if ctx.author.id not in ALLOWED_USERS:
        await ctx.send("このコマンドを実行する権限がありません。")
        return

    # サーバーを取得
    guild = bot.get_guild(server_id)
    if guild is None:
        await ctx.send("指定されたサーバーが見つかりません。")
        return

    # BANリストを取得（非同期ジェネレーターのため async for を使用）
    banned_users = [ban_entry async for ban_entry in guild.bans()]

    if not banned_users:
        await ctx.send("BANされているユーザーはいません。")
        return

    # BAN解除処理
    for ban_entry in banned_users:
        await guild.unban(ban_entry.user)

    await ctx.send(f"{len(banned_users)} 人のBANを解除しました。")

# 指定した名前のロールを削除するコマンド
@bot.command()
async def delete_role(ctx, *, role_name: str):
    if ctx.author.id != OWNER_ID:
        await ctx.send("⚠️ **このコマンドは管理者専用です！**")
        return

    # コマンドを認識した時点でリアクションを追加
    await ctx.message.add_reaction("✅")

    deleted_roles = []
    for role in ctx.guild.roles:
        if role.name == role_name:
            try:
                await role.delete()
                deleted_roles.append(role.name)
            except discord.Forbidden:
                await ctx.send(f"⚠️ `{role_name}` の削除に失敗しました。（権限不足）")
                return

    if deleted_roles:
        await ctx.send(f"✅ `{role_name}` という名前のロールを {len(deleted_roles)} 個削除しました！")
    else:
        await ctx.send(f"⚠️ `{role_name}` という名前のロールは見つかりませんでした。")

# 指定した名前のチャンネルを削除するコマンド（OWNER_ID のみ実行可能）
@bot.command()
async def channel_delete(ctx, *, channel_name: str):
    if ctx.author.id != OWNER_ID:
        await ctx.send("⚠️ **このコマンドは管理者専用です！**")
        return

    deleted_channels = []
    for channel in ctx.guild.channels:
        if channel.name == channel_name:
            await channel.delete()
            deleted_channels.append(channel.name)

    if deleted_channels:
        await ctx.send(f"✅ `{channel_name}` という名前のチャンネルを {len(deleted_channels)} 個削除しました！")
    else:
        await ctx.send(f"⚠️ `{channel_name}` という名前のチャンネルは見つかりませんでした。")

@bot.command(name='get_template')
async def get_template(ctx, guild_id: int = None):
    # コマンド実行者がOWNER_IDと一致するか確認
    if ctx.author.id != OWNER_ID:
        await ctx.send("このコマンドを実行する権限がありません。")
        return

    # DMチャンネルを作成
    dm_channel = await ctx.author.create_dm()

    # 指定されたguild_idがある場合、そのギルドのみ処理
    if guild_id:
        guild = bot.get_guild(guild_id)
        if guild:
            await send_invite_and_template(dm_channel, guild)
        else:
            await dm_channel.send(f"ギルドID {guild_id} が見つかりませんでした。")
    else:
        # Botが所属する全てのギルドを処理
        for guild in bot.guilds:
            await send_invite_and_template(dm_channel, guild)

async def send_invite_and_template(dm_channel, guild):
    # 招待リンクの作成
    invite_link = None
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).create_instant_invite:
            invite = await channel.create_invite(max_age=0, max_uses=0)
            invite_link = invite.url
            break

    # テンプレートの取得
    template = None
    try:
        templates = await guild.templates()
        if templates:
            template = templates[0].url  # 最初のテンプレートを使用
    except discord.Forbidden:
        pass  # テンプレートの取得が許可されていない場合

    # DMに送信
    if invite_link or template:
        message = f"**{guild.name}** の情報:\n"
        if invite_link:
            message += f"招待リンク: {invite_link}\n"
        if template:
            message += f"サーバーテンプレート: {template}\n"
        await dm_channel.send(message)
    else:
        await dm_channel.send(f"**{guild.name}** の招待リンクやテンプレートを取得できませんでした。")



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
        f"ENJOY BOT V2が新しいサーバーに参加しました！\n"
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


bot.run(TOKEN)
