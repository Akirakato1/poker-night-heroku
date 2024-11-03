import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from tabulate import tabulate
from googleapiclient.discovery import build
import matplotlib.pyplot as plt
from collections import defaultdict, Counter
from PIL import Image
import os
import json

class PokerNightManager():
    def __init__(self):
        self.active_night_player_data={}
        self.sheet_prefix="Night"
        self.headers=["PLAYER", "BUYIN", "SCORE"]
        self.max_rows=20
        self.ssid=os.getenv("SSID")
        self.gs_url=f"https://docs.google.com/spreadsheets/d/{self.ssid}"
        self.ssname=os.getenv("SSNAME")
        self.reconnect()
        self.active_night_view=None
    
    def reconnect(self):
        self.connect_gs()
        self.did_to_name, self.name_to_did=self.fetch_players()
        return "Reconnected to googlesheets and re-fetched discord id:name"
    
    def connect_gs(self):
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        self.creds = ServiceAccountCredentials.from_json_keyfile_name("./google-credentials.json", scope)
        self.client = gspread.authorize(self.creds)
        self.sheets_service = build('sheets', 'v4', credentials=self.creds)

    def finish_active_night(self):
        self.active_night_player_data={}
        self.active_night_view=None
        
    def active_night_add_player(self, name):
        if name not in self.active_night_player_data.keys():
            self.active_night_player_data[name]=[1, 0]
    
    def active_night_add_buyin(self, name):
        if name in self.active_night_player_data.keys():
            buyin_score=self.active_night_player_data[name]
            self.active_night_player_data[name]=[buyin_score[0]+1, buyin_score[1]]
    
    def init_active_night_players(self, names=[]):
        self.active_night_player_data={name:[1, 0] for name in names}
    
    def create_new_sheet(self):
        names=list(self.active_night_player_data.keys())
        buyins_scores=list(self.active_night_player_data.values())
        spreadsheet = self.client.open(self.ssname)
        index = int(spreadsheet.worksheets()[-1].title[len(self.sheet_prefix):])+1
        worksheet_name = f"{self.sheet_prefix} {index}"
        worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=self.max_rows, cols=3)
        data=[self.headers]+[[a] + b for a, b in zip(names, buyins_scores)]
        worksheet.update('A1', data)
        bold_request = {
            "requests": [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": worksheet.id,
                            "startRowIndex": 0,  # Row index starts at 0
                            "endRowIndex": 1,  # Only the first row
                            "startColumnIndex": 0,  # Start from the first column (A)
                            "endColumnIndex": 3  # Ending at column B (0-based index)
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {
                                    "bold": True  # Set bold to True
                                }
                            }
                        },
                        "fields": "userEnteredFormat.textFormat.bold"  # Specify that only bold should be modified
                    }}]}
        
        spreadsheet.batch_update(bold_request)
        worksheet_url =  f"{self.gs_url}/edit#gid={worksheet.id}"
        return worksheet_name, worksheet_url
    
    def add_scores_to_night(self, name_score, night):
        spreadsheet = self.client.open(self.ssname)
        try:
            sheet = spreadsheet.get_worksheet(night)
        except:
            return f"Night {night} worksheet not found."
        
        sheet_df=pd.DataFrame(sheet.get_all_records())
        scores_df=pd.DataFrame(name_score, columns=[self.headers[0], self.headers[2]])
        
        if not set(sorted(scores_df['PLAYER'])).issubset(set(sorted(sheet_df['PLAYER']))):
            return "Error: The list of players does not match between the dataframes."

        # Check if all scores in sheet_df are 0
        if not (sheet_df['SCORE'] == 0).all():
            return f"Error: Not all scores in Night {night} are 0."

        # Update the scores in sheet_df based on scores_df
        for index, row in scores_df.iterrows():
            player = row['PLAYER']
            score = row['SCORE']
            # Set the score for the corresponding player in sheet_df
            sheet_df.loc[sheet_df['PLAYER'] == player, 'SCORE'] = score
        
        sheet.update("A2", sheet_df.values.tolist())
        sheet_df=pd.DataFrame(sheet.get_all_records())
        
        return f"Added scores to Night {night}\n```{tabulate(sheet_df, headers='keys', tablefmt='grid', showindex=False)}```"
        
    
    def fetch_players(self):
        spreadsheet = self.client.open(self.ssname)
        sheet = spreadsheet.get_worksheet(0)
        df = pd.DataFrame(sheet.get_all_records())
        did=[did.strip().capitalize() for did in list(df["Discord"])]
        name=[[n.strip().capitalize() for n in ns.split(",")] for ns in list(df["Name"])]
        
        def create_name_to_did_dict(did_list, alias_list):
            name_to_did = {}
            for did, aliases in zip(did_list, alias_list):
                # Map each alias to the same Discord ID
                for alias in aliases:
                    name_to_did[alias] = did
                name_to_did[did]=did

            return name_to_did
        
        return {did[i]:name[i][0] for i in range(len(did))}, create_name_to_did_dict(did, name)
        
    def fetch_all_nights(self):
        spreadsheet = self.client.open(self.ssname)

        # Get all worksheets (tabs) in the spreadsheet
        worksheets = spreadsheet.worksheets()

        # Create ranges for the first 3 columns (A, B, C) and first 20 rows for each worksheet
        ranges = [f"{sheet.title}!A2:C{self.max_rows}" for sheet in worksheets]

        # Batch fetch data from all the worksheets (tabs)
        result = self.sheets_service.spreadsheets().values().batchGet(
            spreadsheetId=self.ssid,
            ranges=ranges
        ).execute()

        dfs=[pd.DataFrame(sheet_data.get('values', []), columns=self.headers) for sheet_data in result['valueRanges'][1:]]
        for df in dfs:
            df.replace('', pd.NA, inplace=True)
            df.dropna(inplace=True)
            df['BUYIN'] = pd.to_numeric(df['BUYIN'], errors='coerce')
            df['SCORE'] = pd.to_numeric(df['SCORE'], errors='coerce')
        return dfs
    
    def normalize_name_score(self, name_score):
        return [[self.did_to_name[self.name_to_did[ns[0]]], ns[1]] for ns in name_score]
    
    def leaderboard(self):
        dfs = self.fetch_all_nights()
        combined_df = pd.concat(dfs)

        result_df = combined_df.groupby('PLAYER', as_index=False).sum()

        result_df['WINNING(CAD)'] = (result_df['SCORE'] / 100) - (result_df['BUYIN'] * 10)

        result_df['WINNING(CAD)'] = result_df['WINNING(CAD)'].round(2)
        result_df = result_df.sort_values(by='WINNING(CAD)', ascending=False)

        def format_winning(value):
            if value < 0:
                return f"-${-value:.2f}"  # Format negative values with $ after -
            else:
                return f"${value:.2f}"  # Format positive values normally

        result_df['WINNING(CAD)'] = result_df['WINNING(CAD)'].apply(format_winning)
        return "**POKER NIGHT LEADERBOARD**\n\n```"+tabulate(result_df, headers='keys', tablefmt='grid', showindex=False)+"```"
    
    def checkdata(self):
        dfs = self.fetch_all_nights()
        issue = []
        for idx, df in enumerate(dfs):
            sum_buyin = df['BUYIN'].sum()
            sum_score = df['SCORE'].sum()
            if not sum_buyin*1000 == sum_score:
                issue.append({
                'night': idx+1,
                'sum_buyin': sum_buyin,
                'sum_score': sum_score})
        if len(issue)==0:
            return "All poker night data scores and buyins consistent"
        else:
            return "```Inconsistent nights detected:\n"+tabulate(pd.DataFrame(issue), headers='keys', tablefmt='grid', showindex=False)+"```"
    
    def personal_stats(self, did):
        did=did.capitalize()
        dfs = self.fetch_all_nights()
        buyins, scores = self.extract_player_data(dfs, did)
        ns_path=self.plot_net_scores(buyins, scores, did)
        bns_path=self.plot_avgnetscores_buyins(buyins, scores, did)
        bp_path=self.plot_buyins_distribution(buyins, did)
        output_path=self.overlay_images_vertically([ns_path, bp_path, bns_path], did)
        
        return output_path

    def plot_buyins_distribution(self, buyins, did, filename='buyins_distribution.jpg'):
        # Count the number of occurrences of each unique buy-in count (number of nights with that exact buy-in count)
        buyin_counts = Counter(buyins)
    
        # Sort the buy-in counts by the number of buy-ins per night
        sorted_buyin_counts = sorted(buyin_counts.items())
        buyin_sizes = [item[0] for item in sorted_buyin_counts]
        night_counts = [item[1] for item in sorted_buyin_counts]
    
        # Create the pie chart
        fig, ax = plt.subplots()
    
        ax.pie(night_counts, labels=buyin_sizes, autopct='%1.1f%%', startangle=140)
        ax.set_title(f'{self.did_to_name[did]}\'s Buy-in Distribution by Number of Nights')
    
        # Save the figure as a JPG file
        fn = f'{did}_{filename}'
        plt.tight_layout()
        plt.savefig(fn)
    
        # Clear the plot to avoid overlap in subsequent plots
        plt.clf()
        return fn

    def plot_avgnetscores_buyins(self, buyins, scores, did, filename='net_scores_buyins.jpg'):
        data = zip(buyins, [scores[i] - buyins[i] * 1000 for i in range(len(buyins))])
        buyin_data = defaultdict(lambda: {'total_net_score': 0, 'count': 0})

            # Loop through the zipped buyins and net scores
        for buyin, net_score in data:
            # Update the total net score and count for each buyin size
            buyin_data[buyin]['total_net_score'] += net_score
            buyin_data[buyin]['count'] += 1

        # Calculate the average net score for each buyin size
        buyin_sizes = sorted(buyin_data.keys())
        #avg_net_scores = [buyin_data[buyin]['total_net_score'] / buyin_data[buyin]['count'] for buyin in buyin_sizes]
        avg_net_scores = [buyin_data[buyin]['total_net_score'] for buyin in buyin_sizes]

        # Create the bar chart
        fig, ax = plt.subplots()

        ax.bar(buyin_sizes, avg_net_scores, color='blue')

        # Add labels and title
        ax.set_xlabel('Buy-in Size')
        ax.set_ylabel('Average Net Score')
        ax.set_title(f'{self.did_to_name[did]}\'s Net Scores by Buy-in Size')
        
        ax.set_xticks(buyin_sizes)
        
        fn=f'{did}_{filename}'
        # Save the figure as a JPG file
        plt.tight_layout()
        plt.savefig(fn)

        # Clear the plot to avoid overlap in subsequent plots
        plt.clf()
        return fn
    
    def plot_net_scores(self, buyins, scores, did, filename='net_scores.jpg'):
        # Calculate net scores
        net_scores = [scores[i] - buyins[i] * 1000 for i in range(len(buyins))]
    
        # Compute cumulative net scores
        cumulative_net_scores = [sum(net_scores[:i+1]) for i in range(len(net_scores))]

        nights = list(range(1, len(buyins) + 1))  # X-axis will be the night indices (1, 2, 3, ...)

        # Create a figure and axis
        fig, ax = plt.subplots()

        # Iterate over cumulative net scores and check for color change when crossing 0
        for i in range(len(cumulative_net_scores) - 1):
            # If there's no crossing, just plot the line segment
            if cumulative_net_scores[i] >= 0 and cumulative_net_scores[i + 1] >= 0:
                ax.plot(nights[i:i+2], cumulative_net_scores[i:i+2], color='blue', marker='o')
            elif cumulative_net_scores[i] < 0 and cumulative_net_scores[i + 1] < 0:
                ax.plot(nights[i:i+2], cumulative_net_scores[i:i+2], color='red', marker='o')
            else:
                # Find the exact crossing point using linear interpolation
                zero_crossing_x = nights[i] + (0 - cumulative_net_scores[i]) / (cumulative_net_scores[i + 1] - cumulative_net_scores[i])

                # First part of the line, from the current point to the zero crossing
                ax.plot([nights[i], zero_crossing_x], [cumulative_net_scores[i], 0], color='blue' if cumulative_net_scores[i] > 0 else 'red')

                # Second part of the line, from the zero crossing to the next point
                ax.plot([zero_crossing_x, nights[i + 1]], [0, cumulative_net_scores[i + 1]], color='blue' if cumulative_net_scores[i + 1] > 0 else 'red')

                # Plot the actual visible markers only for the original data points
                ax.plot(nights[i:i+2], cumulative_net_scores[i:i+2], marker='o', linestyle='None', color='blue' if cumulative_net_scores[i] >= 0 else 'red')
        
        # Add labels and title
        ax.set_xlabel('Nights')
        ax.set_ylabel('Net Score')
        ax.set_title(f'{self.did_to_name[did]}\'s Net Scores')
        
        
        fn=f'{did}_{filename}'
        # Save the figure as a JPG file
        plt.tight_layout()  # Adjust layout to prevent cutoff labels
        plt.savefig(fn)

        # Clear the plot to avoid overlap in subsequent plots
        plt.clf()
        return fn
        
    def extract_player_data(self, dfs, did):
        buyins = []
        scores = []
        player_name=self.did_to_name[did]
        
        for df in dfs:
            if player_name in df['PLAYER'].values:
                player_data = df[df['PLAYER'] == player_name]
                buyins.extend(player_data['BUYIN'].tolist())
                scores.extend(player_data['SCORE'].tolist())

        return buyins, scores
    
    def overlay_images_vertically(self, image_paths, did, filename='combined_image.jpg'):
        # Open all the images from the provided filepaths
        images = [Image.open(image_path) for image_path in image_paths]

        # Calculate the total width and height for the final image
        total_width = max(img.width for img in images)
        total_height = sum(img.height for img in images)

        # Create a white background of the appropriate size
        combined_image = Image.new('RGB', (total_width, total_height), color=(255, 255, 255))

        # Paste the images onto the white background
        y_offset = 0
        for img in images:
            combined_image.paste(img, (0, y_offset))
            y_offset += img.height
        
        fn=f'{did}_{filename}'
        # Save the final combined image
        combined_image.save(fn)

        # Delete the original images
        for image_path in image_paths:
            os.remove(image_path)
            
        return fn
