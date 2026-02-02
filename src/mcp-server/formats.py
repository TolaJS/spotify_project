from mcp.types import TextContent

def format_tracks(tracks, query):
    if not tracks:
        return [TextContent(type="text", text=f"No tracks found for '{query}'")]
    
    text = f"Found {len(tracks)} track(s):\n\n"
    for i, track in enumerate(tracks, 1):
        artists = ", ".join([a["name"] for a in track["artists"]])
        album = track["album"]["name"]
        duration_min = track["duration_ms"] // 60000
        duration_sec = (track["duration_ms"] % 60000) // 1000
        
        text += f"{i}. {track['name']}\n"
        text += f"   Artist(s): {artists}\n"
        text += f"   Album: {album}\n"
        text += f"   Duration: {duration_min}:{duration_sec:02d}\n"
        text += f"   URI: {track['uri']}\n\n"
    
    return [TextContent(type="text", text=text)]

def format_artists(artists, query):
    if not artists:
        return [TextContent(type="text", text=f"No artists found for '{query}'")]
    
    text = f"Found {len(artists)} artist(s):\n\n"
    for i, artist in enumerate(artists, 1):
        genres = ", ".join(artist["genres"][:3]) if artist["genres"] else "No genres listed"
        popularity = artist.get("popularity", 0)
        followers = artist["followers"]["total"]
        
        text += f"{i}. {artist['name']}\n"
        text += f"   Genres: {genres}\n"
        text += f"   Popularity: {popularity}/100\n"
        text += f"   Followers: {followers:,}\n"
        text += f"   URI: {artist['uri']}\n\n"
    
    return [TextContent(type="text", text=text)]

def format_albums(albums, query):
    if not albums:
        return [TextContent(type="text", text=f"No albums found for '{query}'")]
    
    text = f"Found {len(albums)} album(s):\n\n"
    for i, album in enumerate(albums, 1):
        artists = ", ".join([a["name"] for a in album["artists"]])
        year = album["release_date"][:4] if album.get("release_date") else "Unknown"
        
        text += f"{i}. {album['name']}\n"
        text += f"   Artist(s): {artists}\n"
        text += f"   Release Year: {year}\n"
        text += f"   Tracks: {album['total_tracks']}\n"
        text += f"   URI: {album['uri']}\n\n"
    
    return [TextContent(type="text", text=text)]
