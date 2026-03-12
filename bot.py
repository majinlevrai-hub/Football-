"""
Bot Discord de Paris Sportifs
Système de matchs numérotés (1-30) avec gestion manuelle par les admins
Paiement via CoinsBot avec commande &pay
"""

import discord
from discord.ext import commands
from discord.ui import View, Button
import os
import json
from datetime import datetime
from dotenv import load_dotenv

# ========== CONFIGURATION ==========
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
COINSBOT_USER_ID = int(os.getenv('COINSBOT_USER_ID'))
ADMIN_ROLE_ID = int(os.getenv('ADMIN_ROLE_ID'))

# Configuration Discord
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Fichiers de stockage
BETS_FILE = 'bets.json'
MATCHES_FILE = 'matches.json'


# ========== FONCTIONS UTILITAIRES ==========

def load_data(filename):
    """Charge les données depuis un fichier JSON"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_data(filename, data):
    """Sauvegarde les données dans un fichier JSON"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def initialize_matches():
    """Initialise 30 matchs vides au premier lancement"""
    matches = load_data(MATCHES_FILE)
    if not matches:
        matches = {str(i): None for i in range(1, 31)}
        save_data(MATCHES_FILE, matches)
    return matches


# ========== INTERFACE DE PARIS (BOUTONS) ==========

class BetView(View):
    """Interface avec boutons pour placer un pari"""
    
    def __init__(self, match_num, home_team, away_team, odds):
        super().__init__(timeout=None)
        self.match_num = match_num
        self.home_team = home_team
        self.away_team = away_team
        self.odds = odds
        
    @discord.ui.button(label="🏠 Domicile", style=discord.ButtonStyle.green, custom_id="bet_home")
    async def bet_home(self, interaction: discord.Interaction, button: Button):
        await self.process_bet(interaction, "home")
    
    @discord.ui.button(label="⚖️ Nul", style=discord.ButtonStyle.grey, custom_id="bet_draw")
    async def bet_draw(self, interaction: discord.Interaction, button: Button):
        await self.process_bet(interaction, "draw")
    
    @discord.ui.button(label="✈️ Extérieur", style=discord.ButtonStyle.blurple, custom_id="bet_away")
    async def bet_away(self, interaction: discord.Interaction, button: Button):
        await self.process_bet(interaction, "away")
    
    async def process_bet(self, interaction: discord.Interaction, bet_type):
        """Traite le processus complet d'un pari"""
        user_id = str(interaction.user.id)
        bets = load_data(BETS_FILE)
        
        # Vérifier si l'utilisateur a déjà parié sur ce match
        if self.match_num in bets and user_id in bets[self.match_num].get('bets', {}):
            await interaction.response.send_message(
                "❌ Vous avez déjà parié sur ce match !",
                ephemeral=True
            )
            return
        
        # Afficher la cote
        odd_value = self.odds.get(bet_type, 2.0)
        bet_names = {
            'home': f"{self.home_team} (cote {odd_value})",
            'draw': f"Match Nul (cote {odd_value})",
            'away': f"{self.away_team} (cote {odd_value})"
        }
        
        await interaction.response.send_message(
            f"💰 Combien voulez-vous parier sur **{bet_names[bet_type]}** ?\n"
            f"Répondez avec un montant (ex: 100)",
            ephemeral=True
        )
        
        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id
        
        try:
            # Attendre le montant
            msg = await bot.wait_for('message', check=check, timeout=30.0)
            amount = int(msg.content)
            
            if amount <= 0:
                await interaction.followup.send("❌ Le montant doit être positif !", ephemeral=True)
                return
            
            # Demander le paiement via CoinsBot
            payment_msg = await interaction.channel.send(
                f"💳 {interaction.user.mention}, **envoyez votre paiement maintenant** :\n"
                f"```&pay @CoinsBot {amount}```\n\n"
                f"⏳ Vous avez **2 minutes** pour envoyer le paiement.\n"
                f"✅ Cliquez sur ✅ une fois le paiement envoyé\n"
                f"❌ Cliquez sur ❌ pour annuler"
            )
            await payment_msg.add_reaction("✅")
            await payment_msg.add_reaction("❌")
            
            def reaction_check(reaction, user):
                return user.id == interaction.user.id and str(reaction.emoji) in ["✅", "❌"]
            
            reaction, user = await bot.wait_for('reaction_add', check=reaction_check, timeout=120.0)
            
            if str(reaction.emoji) == "✅":
                # Enregistrer le pari
                if self.match_num not in bets:
                    bets[self.match_num] = {
                        'home_team': self.home_team,
                        'away_team': self.away_team,
                        'odds': self.odds,
                        'bets': {}
                    }
                
                bets[self.match_num]['bets'][user_id] = {
                    'username': str(interaction.user),
                    'bet_type': bet_type,
                    'amount': amount,
                    'odd': odd_value,
                    'timestamp': datetime.now().isoformat()
                }
                
                save_data(BETS_FILE, bets)
                
                potential_win = int(amount * odd_value)
                
                await interaction.followup.send(
                    f"✅ **Pari enregistré !**\n"
                    f"🏟️ Match #{self.match_num} : {self.home_team} vs {self.away_team}\n"
                    f"🎯 Pari : {bet_names[bet_type]}\n"
                    f"💰 Mise : {amount} coins\n"
                    f"🎁 Gain potentiel : {potential_win} coins",
                    ephemeral=True
                )
                await payment_msg.delete()
            else:
                await interaction.followup.send("❌ Pari annulé.", ephemeral=True)
                await payment_msg.delete()
                
        except TimeoutError:
            await interaction.followup.send("⏱️ Temps écoulé, pari annulé.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("❌ Montant invalide !", ephemeral=True)


# ========== ÉVÉNEMENTS DU BOT ==========

@bot.event
async def on_ready():
    """Événement déclenché quand le bot est connecté"""
    print(f'✅ Bot connecté en tant que {bot.user}')
    print(f'📊 Serveurs : {len(bot.guilds)}')
    initialize_matches()


# ========== COMMANDES JOUEURS ==========

@bot.command(name='matchs')
async def show_matches(ctx):
    """Affiche tous les matchs disponibles (1-30)"""
    matches = load_data(MATCHES_FILE)
    
    active_matches = {num: data for num, data in matches.items() if data is not None}
    
    if not active_matches:
        await ctx.send("📭 Aucun match disponible pour le moment.\n"
                      "Les admins ajouteront bientôt des matchs !")
        return
    
    embed = discord.Embed(
        title="⚽ Matchs disponibles pour parier",
        description=f"**{len(active_matches)} match(s) disponible(s)**",
        color=discord.Color.blue()
    )
    
    for match_num in sorted(active_matches.keys(), key=int):
        match = active_matches[match_num]
        odds = match.get('odds', {'home': 2.0, 'draw': 3.0, 'away': 2.0})
        status = "🔒 Fermé" if match.get('closed', False) else "🟢 Ouvert"
        
        embed.add_field(
            name=f"🔢 Match #{match_num} - {status}",
            value=f"**{match['home_team']} vs {match['away_team']}**\n"
                  f"📊 Cotes : {odds['home']} / {odds['draw']} / {odds['away']}\n"
                  f"➡️ `!parier {match_num}`",
            inline=False
        )
    
    embed.set_footer(text="Utilisez !parier <numéro> pour placer un pari")
    await ctx.send(embed=embed)


@bot.command(name='parier')
async def place_bet(ctx, match_num: int):
    """Placer un pari sur un match"""
    if match_num < 1 or match_num > 30:
        await ctx.send("❌ Numéro de match invalide. Utilisez un numéro entre 1 et 30.")
        return
    
    matches = load_data(MATCHES_FILE)
    match_key = str(match_num)
    
    if match_key not in matches or matches[match_key] is None:
        await ctx.send(f"❌ Match #{match_num} non disponible.\n"
                      f"Utilisez `!matchs` pour voir les matchs actifs.")
        return
    
    match = matches[match_key]
    
    # Vérifier si les paris sont ouverts
    if match.get('closed', False):
        await ctx.send(f"❌ Les paris sont fermés pour le match #{match_num} !")
        return
    
    odds = match.get('odds', {'home': 2.0, 'draw': 3.0, 'away': 2.0})
    
    embed = discord.Embed(
        title=f"⚽ Parier sur le Match #{match_num}",
        description=f"**{match['home_team']} vs {match['away_team']}**",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name="📊 Cotes disponibles",
        value=f"🏠 Domicile : **{odds['home']}**\n"
              f"⚖️ Nul : **{odds['draw']}**\n"
              f"✈️ Extérieur : **{odds['away']}**",
        inline=False
    )
    
    embed.add_field(
        name="💡 Comment parier ?",
        value="1️⃣ Cliquez sur un bouton ci-dessous\n"
              "2️⃣ Indiquez votre mise\n"
              "3️⃣ Envoyez le paiement avec `&pay @CoinsBot [montant]`\n"
              "4️⃣ Validez avec ✅",
        inline=False
    )
    
    view = BetView(match_key, match['home_team'], match['away_team'], odds)
    await ctx.send(embed=embed, view=view)


@bot.command(name='mesparis')
async def my_bets(ctx):
    """Afficher vos paris en cours"""
    bets = load_data(BETS_FILE)
    user_id = str(ctx.author.id)
    
    user_bets = []
    total_mise = 0
    total_potential = 0
    
    for match_num, match_data in bets.items():
        if user_id in match_data.get('bets', {}):
            bet = match_data['bets'][user_id]
            user_bets.append((match_num, match_data, bet))
            total_mise += bet['amount']
            total_potential += int(bet['amount'] * bet['odd'])
    
    if not user_bets:
        await ctx.send("📭 Vous n'avez aucun pari en cours.")
        return
    
    embed = discord.Embed(
        title="🎰 Vos paris en cours",
        description=f"**{len(user_bets)} pari(s) actif(s)**",
        color=discord.Color.gold()
    )
    
    for match_num, match_data, bet in user_bets:
        bet_names = {
            'home': f"🏠 {match_data['home_team']}",
            'draw': "⚖️ Match Nul",
            'away': f"✈️ {match_data['away_team']}"
        }
        
        potential_win = int(bet['amount'] * bet['odd'])
        
        embed.add_field(
            name=f"Match #{match_num} : {match_data['home_team']} vs {match_data['away_team']}",
            value=f"Pari : {bet_names[bet['bet_type']]}\n"
                  f"💰 Mise : {bet['amount']} coins (cote {bet['odd']})\n"
                  f"🎁 Gain potentiel : {potential_win} coins",
            inline=False
        )
    
    embed.set_footer(text=f"Total misé : {total_mise} coins | Gains potentiels : {total_potential} coins")
    await ctx.send(embed=embed)


# ========== COMMANDES ADMIN ==========

@bot.command(name='definir')
async def define_match(ctx, match_num: int, home_team: str, away_team: str):
    """[ADMIN] Définir un match (ex: !definir 5 PSG Monaco)"""
    if not any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles):
        await ctx.send("❌ Vous n'avez pas la permission.")
        return
    
    if match_num < 1 or match_num > 30:
        await ctx.send("❌ Numéro invalide. Utilisez 1-30.")
        return
    
    matches = load_data(MATCHES_FILE)
    match_key = str(match_num)
    
    matches[match_key] = {
        'home_team': home_team,
        'away_team': away_team,
        'odds': {'home': 2.0, 'draw': 3.0, 'away': 2.0},
        'closed': False,
        'created_at': datetime.now().isoformat()
    }
    
    save_data(MATCHES_FILE, matches)
    
    await ctx.send(f"✅ **Match #{match_num} créé !**\n"
                  f"🏟️ **{home_team} vs {away_team}**\n"
                  f"📊 Cotes par défaut : 2.0 / 3.0 / 2.0\n\n"
                  f"💡 Utilisez `!cotes {match_num} <dom> <nul> <ext>` pour personnaliser les cotes.")


@bot.command(name='cotes')
async def set_odds(ctx, match_num: int, home_odd: float, draw_odd: float, away_odd: float):
    """[ADMIN] Définir les cotes (ex: !cotes 5 1.8 3.2 2.1)"""
    if not any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles):
        await ctx.send("❌ Vous n'avez pas la permission.")
        return
    
    matches = load_data(MATCHES_FILE)
    match_key = str(match_num)
    
    if match_key not in matches or matches[match_key] is None:
        await ctx.send(f"❌ Match #{match_num} n'existe pas. Utilisez `!definir` d'abord.")
        return
    
    matches[match_key]['odds'] = {
        'home': home_odd,
        'draw': draw_odd,
        'away': away_odd
    }
    
    save_data(MATCHES_FILE, matches)
    
    match = matches[match_key]
    await ctx.send(f"✅ **Cotes mises à jour pour le match #{match_num} !**\n"
                  f"🏟️ {match['home_team']} vs {match['away_team']}\n"
                  f"📊 **Nouvelles cotes : {home_odd} / {draw_odd} / {away_odd}**")


@bot.command(name='fermer')
async def close_bets(ctx, match_num: int):
    """[ADMIN] Fermer les paris pour un match"""
    if not any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles):
        await ctx.send("❌ Vous n'avez pas la permission.")
        return
    
    matches = load_data(MATCHES_FILE)
    match_key = str(match_num)
    
    if match_key not in matches or matches[match_key] is None:
        await ctx.send(f"❌ Match #{match_num} n'existe pas.")
        return
    
    matches[match_key]['closed'] = True
    save_data(MATCHES_FILE, matches)
    
    match = matches[match_key]
    await ctx.send(f"🔒 **Paris fermés pour le match #{match_num} !**\n"
                  f"🏟️ {match['home_team']} vs {match['away_team']}")


@bot.command(name='resultat')
async def set_result(ctx, match_num: int, result: str):
    """[ADMIN] Définir le résultat (ex: !resultat 5 home)"""
    if not any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles):
        await ctx.send("❌ Vous n'avez pas la permission.")
        return
    
    if result not in ['home', 'draw', 'away']:
        await ctx.send("❌ Résultat invalide. Utilisez : `home`, `draw` ou `away`")
        return
    
    bets = load_data(BETS_FILE)
    match_key = str(match_num)
    
    if match_key not in bets:
        await ctx.send(f"❌ Aucun pari trouvé pour le match #{match_num}.")
        return
    
    match_data = bets[match_key]
    winners = []
    losers = []
    total_gains = 0
    
    for user_id, bet in match_data['bets'].items():
        if bet['bet_type'] == result:
            gain = int(bet['amount'] * bet['odd'])
            winners.append((user_id, bet, gain))
            total_gains += gain
        else:
            losers.append((user_id, bet))
    
    embed = discord.Embed(
        title=f"📊 Résultats du Match #{match_num}",
        description=f"**{match_data['home_team']} vs {match_data['away_team']}**",
        color=discord.Color.green()
    )
    
    result_names = {
        'home': f"🏠 Victoire {match_data['home_team']}",
        'draw': "⚖️ Match Nul",
        'away': f"✈️ Victoire {match_data['away_team']}"
    }
    
    embed.add_field(name="🏆 Résultat", value=result_names[result], inline=False)
    
    if winners:
        winners_text = "\n".join([
            f"<@{uid}> : {bet['amount']} coins (x{bet['odd']}) → **gagne {gain} coins** 🎉"
            for uid, bet, gain in winners
        ])
        embed.add_field(name=f"✅ Gagnants ({len(winners)})", value=winners_text, inline=False)
    else:
        embed.add_field(name="✅ Gagnants", value="Aucun gagnant", inline=False)
    
    if losers:
        losers_text = "\n".join([
            f"<@{uid}> : perd {bet['amount']} coins"
            for uid, bet in losers[:10]
        ])
        if len(losers) > 10:
            losers_text += f"\n... et {len(losers) - 10} autre(s)"
        embed.add_field(name=f"❌ Perdants ({len(losers)})", value=losers_text, inline=False)
    
    embed.set_footer(text=f"Total des gains distribués : {total_gains} coins")
    
    await ctx.send(embed=embed)
    
    # Supprimer le match des paris actifs
    del bets[match_key]
    save_data(BETS_FILE, bets)
    
    # Marquer le match comme clôturé
    matches = load_data(MATCHES_FILE)
    if match_key in matches:
        matches[match_key] = None
        save_data(MATCHES_FILE, matches)


@bot.command(name='reset')
async def reset_match(ctx, match_num: int):
    """[ADMIN] Supprimer un match"""
    if not any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles):
        await ctx.send("❌ Vous n'avez pas la permission.")
        return
    
    matches = load_data(MATCHES_FILE)
    match_key = str(match_num)
    
    matches[match_key] = None
    save_data(MATCHES_FILE, matches)
    
    await ctx.send(f"🗑️ Match #{match_num} supprimé !")


# ========== COMMANDE D'AIDE ==========

@bot.command(name='aide')
async def help_command(ctx):
    """Afficher l'aide complète"""
    embed = discord.Embed(
        title="📖 Guide complet du Bot de Paris Sportifs",
        description="Système de matchs numérotés (1-30) avec paiement via CoinsBot",
        color=discord.Color.purple()
    )
    
    embed.add_field(
        name="👥 Commandes Joueurs",
        value="**!matchs** - Voir tous les matchs disponibles\n"
              "**!parier <numéro>** - Parier sur un match spécifique\n"
              "**!mesparis** - Voir vos paris actifs et gains potentiels\n"
              "**!aide** - Afficher ce message",
        inline=False
    )
    
    embed.add_field(
        name="👑 Commandes Admins",
        value="**!definir <num> <equipe1> <equipe2>** - Créer un nouveau match\n"
              "**!cotes <num> <dom> <nul> <ext>** - Définir/modifier les cotes\n"
              "**!fermer <num>** - Fermer les paris d'un match\n"
              "**!resultat <num> <home/draw/away>** - Définir le résultat et distribuer les gains\n"
              "**!reset <num>** - Supprimer un match",
        inline=False
    )
    
    embed.add_field(
        name="💡 Exemple d'utilisation (Admin)",
        value="```\n"
              "!definir 5 PSG Monaco\n"
              "!cotes 5 1.8 3.2 2.1\n"
              "!fermer 5\n"
              "!resultat 5 home\n"
              "```",
        inline=False
    )
    
    embed.add_field(
        name="💰 Comment parier ?",
        value="1. Utilisez `!parier <numéro>` pour choisir un match\n"
              "2. Cliquez sur le bouton de votre choix (Domicile/Nul/Extérieur)\n"
              "3. Indiquez le montant de votre mise\n"
              "4. Envoyez le paiement avec : `&pay @CoinsBot <montant>`\n"
              "5. Cliquez sur ✅ pour valider votre pari",
        inline=False
    )
    
    embed.set_footer(text="30 matchs disponibles (numéros 1-30) | Paiement via CoinsBot")
    await ctx.send(embed=embed)


# ========== LANCEMENT DU BOT ==========

if __name__ == "__main__":
    bot.run(TOKEN)
