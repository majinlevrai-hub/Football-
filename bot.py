import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import os
import json
import aiohttp
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
FOOTBALL_API_KEY = os.getenv('FOOTBALL_API_KEY')
COINSBOT_USER_ID = int(os.getenv('COINSBOT_USER_ID'))
ADMIN_ROLE_ID = int(os.getenv('ADMIN_ROLE_ID'))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Stockage des données
BETS_FILE = 'bets.json'
MATCHES_FILE = 'matches.json'

# Compétitions supportées
LEAGUES = {
    'ligue1': {'id': 61, 'name': 'Ligue 1', 'emoji': '🇫🇷'},
    'pl': {'id': 39, 'name': 'Premier League', 'emoji': '🏴󠁧󠁢󠁥󠁮󠁧󠁿'},
    'ucl': {'id': 2, 'name': 'Champions League', 'emoji': '🏆'},
    'europa': {'id': 3, 'name': 'Europa League', 'emoji': '🌍'}
}

def load_data(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_data(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

async def fetch_matches(league_id):
    """Données de test - matchs fictifs"""
    return [
        {
            "fixture": {"id": 123456},
            "teams": {
                "home": {"name": "PSG"},
                "away": {"name": "OM"}
            }
        },
        {
            "fixture": {"id": 123457, "date": "2026-03-15T20:45:00Z"},
            "teams": {
                "home": {"name": "Lyon"},
                "away": {"name": "Monaco"}
            }
        }
    ]

    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get('response', [])
    return []

class BetView(View):
    def __init__(self, match_id, home_team, away_team):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.home_team = home_team
        self.away_team = away_team
        
    @discord.ui.button(label="Domicile", style=discord.ButtonStyle.green, custom_id="bet_home")
    async def bet_home(self, interaction: discord.Interaction, button: Button):
        await self.process_bet(interaction, "home")
    
    @discord.ui.button(label="Nul", style=discord.ButtonStyle.grey, custom_id="bet_draw")
    async def bet_draw(self, interaction: discord.Interaction, button: Button):
        await self.process_bet(interaction, "draw")
    
    @discord.ui.button(label="Extérieur", style=discord.ButtonStyle.blurple, custom_id="bet_away")
    async def bet_away(self, interaction: discord.Interaction, button: Button):
        await self.process_bet(interaction, "away")
    
    async def process_bet(self, interaction: discord.Interaction, bet_type):
        user_id = str(interaction.user.id)
        
        # Charger les paris existants
        bets = load_data(BETS_FILE)
        
        # Vérifier si l'utilisateur a déjà parié sur ce match
        if self.match_id in bets:
            if user_id in bets[self.match_id]['bets']:
                await interaction.response.send_message(
                    "❌ Vous avez déjà parié sur ce match !",
                    ephemeral=True
                )
                return
        
        # Demander le montant
        await interaction.response.send_message(
            f"💰 Combien voulez-vous parier ? Répondez avec un montant (ex: 100)",
            ephemeral=True
        )
        
        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id
        
        try:
            msg = await bot.wait_for('message', check=check, timeout=30.0)
            amount = int(msg.content)
            
            if amount <= 0:
                await interaction.followup.send("❌ Le montant doit être positif !", ephemeral=True)
                return
            
            # Demander le paiement via CoinsBot
            payment_msg = await interaction.channel.send(
                f"{interaction.user.mention}, envoyez {amount} coins à <@{COINSBOT_USER_ID}> avec la commande :\n"
                f"```/pay @CoinsBot {amount}```\n"
                f"Une fois fait, cliquez sur ✅"
            )
            await payment_msg.add_reaction("✅")
            await payment_msg.add_reaction("❌")
            
            def reaction_check(reaction, user):
                return user.id == interaction.user.id and str(reaction.emoji) in ["✅", "❌"]
            
            reaction, user = await bot.wait_for('reaction_add', check=reaction_check, timeout=120.0)
            
            if str(reaction.emoji) == "✅":
                # Enregistrer le pari
                if self.match_id not in bets:
                    bets[self.match_id] = {
                        'home_team': self.home_team,
                        'away_team': self.away_team,
                        'bets': {}
                    }
                
                bets[self.match_id]['bets'][user_id] = {
                    'username': str(interaction.user),
                    'bet_type': bet_type,
                    'amount': amount,
                    'timestamp': datetime.now().isoformat()
                }
                
                save_data(BETS_FILE, bets)
                
                bet_names = {
                    'home': self.home_team,
                    'draw': 'Match Nul',
                    'away': self.away_team
                }
                
                await interaction.followup.send(
                    f"✅ Pari enregistré !\n"
                    f"Match : {self.home_team} vs {self.away_team}\n"
                    f"Pari : {bet_names[bet_type]}\n"
                    f"Montant : {amount} coins",
                    ephemeral=True
                )
            else:
                await interaction.followup.send("❌ Pari annulé.", ephemeral=True)
                
        except TimeoutError:
            await interaction.followup.send("⏱️ Temps écoulé, pari annulé.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("❌ Montant invalide !", ephemeral=True)

@bot.event
async def on_ready():
    print(f'✅ Bot connecté en tant que {bot.user}')
    check_matches.start()

@bot.command(name='matchs')
async def show_matches(ctx, league: str = 'ligue1'):
    """Affiche les matchs à venir pour une compétition"""
    league = league.lower()
    
    if league not in LEAGUES:
        await ctx.send(f"❌ Compétition invalide. Utilisez : {', '.join(LEAGUES.keys())}")
        return
    
    league_info = LEAGUES[league]
    matches = await fetch_matches(league_info['id'])
    
    if not matches:
        await ctx.send(f"Aucun match à venir pour {league_info['name']}")
        return
    
    embed = discord.Embed(
        title=f"{league_info['emoji']} {league_info['name']} - Matchs à venir",
        color=discord.Color.blue()
    )
    
    matches_data = load_data(MATCHES_FILE)
    
    for match in matches[:5]:  # Limiter à 5 matchs
        fixture = match['fixture']
        teams = match['teams']
        
        match_id = str(fixture['id'])
        date = datetime.fromisoformat(fixture['date'].replace('Z', '+00:00'))
        
        # Sauvegarder le match
        matches_data[match_id] = {
            'league': league,
            'home_team': teams['home']['name'],
            'away_team': teams['away']['name'],
            'date': fixture['date'],
            'status': fixture['status']['short']
        }
        
        embed.add_field(
            name=f"{teams['home']['name']} vs {teams['away']['name']}",
            value=f"📅 {date.strftime('%d/%m/%Y %H:%M')}\n🆔 Match ID: {match_id}",
            inline=False
        )
    
    save_data(MATCHES_FILE, matches_data)
    await ctx.send(embed=embed)

@bot.command(name='parier')
async def place_bet(ctx, match_id: str):
    """Placer un pari sur un match"""
    matches = load_data(MATCHES_FILE)
    
    if match_id not in matches:
        await ctx.send("❌ Match introuvable. Utilisez `!matchs` pour voir les matchs disponibles.")
        return
    
    match = matches[match_id]
    
    # Vérifier si le match n'a pas commencé
    match_date = datetime.fromisoformat(match['date'].replace('Z', '+00:00'))
    if datetime.now(match_date.tzinfo) >= match_date:
        await ctx.send("❌ Les paris sont fermés, le match a déjà commencé !")
        return
    
    embed = discord.Embed(
        title="⚽ Placer un pari",
        description=f"**{match['home_team']} vs {match['away_team']}**\n"
                    f"📅 {match_date.strftime('%d/%m/%Y %H:%M')}",
        color=discord.Color.green()
    )
    
    embed.add_field(name="Comment parier ?", value="Cliquez sur un bouton ci-dessous :", inline=False)
    
    view = BetView(match_id, match['home_team'], match['away_team'])
    await ctx.send(embed=embed, view=view)

@bot.command(name='mesparis')
async def my_bets(ctx):
    """Afficher vos paris en cours"""
    bets = load_data(BETS_FILE)
    user_id = str(ctx.author.id)
    
    user_bets = []
    for match_id, match_data in bets.items():
        if user_id in match_data['bets']:
            user_bets.append((match_id, match_data))
    
    if not user_bets:
        await ctx.send("Vous n'avez aucun pari en cours.")
        return
    
    embed = discord.Embed(
        title="🎰 Vos paris en cours",
        color=discord.Color.gold()
    )
    
    for match_id, match_data in user_bets:
        bet = match_data['bets'][user_id]
        bet_names = {
            'home': match_data['home_team'],
            'draw': 'Match Nul',
            'away': match_data['away_team']
        }
        
        embed.add_field(
            name=f"{match_data['home_team']} vs {match_data['away_team']}",
            value=f"Pari : {bet_names[bet['bet_type']]}\n💰 Montant : {bet['amount']} coins",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='resultats')
@commands.has_role(ADMIN_ROLE_ID)
async def set_results(ctx, match_id: str, result: str):
    """[ADMIN] Définir le résultat d'un match (home/draw/away)"""
    if result not in ['home', 'draw', 'away']:
        await ctx.send("❌ Résultat invalide. Utilisez : home, draw ou away")
        return
    
    bets = load_data(BETS_FILE)
    
    if match_id not in bets:
        await ctx.send("❌ Aucun pari trouvé pour ce match.")
        return
    
    match_data = bets[match_id]
    winners = []
    losers = []
    
    for user_id, bet in match_data['bets'].items():
        if bet['bet_type'] == result:
            winners.append((user_id, bet))
        else:
            losers.append((user_id, bet))
    
    # Calculer les gains (cote simple 2.0 pour l'exemple)
    total_pool = sum(bet['amount'] for _, bet in match_data['bets'].values())
    
    embed = discord.Embed(
        title=f"📊 Résultats : {match_data['home_team']} vs {match_data['away_team']}",
        color=discord.Color.green()
    )
    
    result_names = {
        'home': match_data['home_team'],
        'draw': 'Match Nul',
        'away': match_data['away_team']
    }
    
    embed.add_field(name="Résultat", value=result_names[result], inline=False)
    
    if winners:
        winners_text = "\n".join([
            f"<@{uid}> : {bet['amount']} coins → gagne {bet['amount'] * 2} coins"
            for uid, bet in winners
        ])
        embed.add_field(name="🎉 Gagnants", value=winners_text, inline=False)
    
    if losers:
        losers_text = "\n".join([
            f"<@{uid}> : perd {bet['amount']} coins"
            for uid, bet in losers
        ])
        embed.add_field(name="😢 Perdants", value=losers_text, inline=False)
    
    await ctx.send(embed=embed)
    
    # Supprimer le match des paris actifs
    del bets[match_id]
    save_data(BETS_FILE, bets)

@tasks.loop(minutes=5)
async def check_matches():
    """Vérifier les matchs qui commencent bientôt"""
    matches = load_data(MATCHES_FILE)
    bets = load_data(BETS_FILE)
    
    now = datetime.now()
    
    for match_id, match in list(matches.items()):
        match_date = datetime.fromisoformat(match['date'].replace('Z', '+00:00'))
        
        # Fermer les paris 5 minutes avant le début
        if now >= match_date - timedelta(minutes=5) and match_id in bets:
            print(f"🔒 Paris fermés pour : {match['home_team']} vs {match['away_team']}")

@bot.command(name='classement')
async def leaderboard(ctx):
    """Afficher le classement des meilleurs parieurs"""
    await ctx.send("🏆 Fonctionnalité à venir : Classement des meilleurs parieurs")

@bot.command(name='aide')
async def help_command(ctx):
    """Afficher l'aide"""
    embed = discord.Embed(
        title="📖 Guide des commandes",
        description="Bot de paris sportifs sur le football",
        color=discord.Color.purple()
    )
    
    embed.add_field(
        name="!matchs [ligue1/pl/ucl/europa]",
        value="Afficher les matchs à venir",
        inline=False
    )
    embed.add_field(
        name="!parier <match_id>",
        value="Placer un pari sur un match",
        inline=False
    )
    embed.add_field(
        name="!mesparis",
        value="Voir vos paris en cours",
        inline=False
    )
    embed.add_field(
        name="!classement",
        value="Voir le classement",
        inline=False
    )
    
    await ctx.send(embed=embed)

bot.run(TOKEN)
