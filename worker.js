export default {
  async fetch(request) {
    const url = new URL(request.url);
    
    // Simple homepage
    const html = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ClearShot - Trucking Road Intelligence</title>
    <style>
        body { 
            font-family: system-ui, Arial, sans-serif; 
            text-align: center; 
            padding: 60px 20px; 
            background: #0f172a; 
            color: #e2e8f0; 
            line-height: 1.6;
        }
        h1 { color: #22d3ee; margin-bottom: 10px; }
        .tagline { color: #67e8f9; font-size: 1.3em; }
        a { color: #67e8f9; text-decoration: none; font-weight: bold; }
        a:hover { text-decoration: underline; }
        .download { 
            display: inline-block; 
            margin: 30px 10px; 
            padding: 15px 30px; 
            background: #22d3ee; 
            color: #0f172a; 
            border-radius: 8px; 
            font-size: 1.2em;
        }
    </style>
</head>
<body>
    <h1>🚛 ClearShot</h1>
    <p class="tagline">Road Hazards • DOT 511 • Weather • HOS Guardian</p>
    <p>Built for truckers, by a trucker.</p>
    
    <a href="https://github.com/arbymcpatriot3/CleanShot/releases" class="download" target="_blank">
        ⬇️ Download Latest Version
    </a><br><br>
    
    <p><a href="https://github.com/arbymcpatriot3/CleanShot" target="_blank">View Full Project on GitHub</a></p>
    <p>Full dashboard and premium features coming soon.</p>
</body>
</html>`;

    return new Response(html, {
      headers: { "Content-Type": "text/html;charset=UTF-8" }
    });
  }
};