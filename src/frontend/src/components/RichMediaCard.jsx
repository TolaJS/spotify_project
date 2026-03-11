import React from 'react';

function RichMediaCard({ item }) {
    // We expect item to have at minimum { uri: "spotify:track:1234..." }
    if (!item || !item.uri) return null;

    // Extract the type and ID from the URI
    // e.g. "spotify:track:4cOdK2wGLETKBW3PvgPWqT" -> type "track", id "4cOd..."
    const parts = item.uri.split(':');
    if (parts.length !== 3 || parts[0] !== 'spotify') return null;

    const type = parts[1]; // track, artist, album, playlist
    const id = parts[2];

    // Spotify embed URL format
    const embedUrl = `https://open.spotify.com/embed/${type}/${id}?utm_source=generator&theme=0`;

    return (
        <div className="bg-[#181818] rounded-xl overflow-hidden shadow-lg border border-spotify-grey/50 hover:border-spotify-lightgrey/30 transition-colors w-full max-w-sm my-2">
            <iframe
                style={{ borderRadius: '12px' }}
                src={embedUrl}
                width="100%"
                height={type === 'track' ? "152" : "352"}
                frameBorder="0"
                allowFullScreen=""
                allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
                loading="lazy"
                title={`Spotify ${type} embed`}
            ></iframe>
        </div>
    );
}

export default RichMediaCard;
