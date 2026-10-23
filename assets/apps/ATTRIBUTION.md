# App artwork

Bundled PNG images identify their respective applications and publishers. Names and logos remain the trademarks of their respective owners; inclusion does not imply endorsement.

Per-app source URLs and native dimensions are recorded in sources.json. Images retain their proportions on transparent 256px canvases; smaller vendor originals are not artificially enlarged. The application downsamples these masters to 80px using Lanczos filtering and makes no runtime icon requests.

Dashboard Icons by homarr-labs and contributors: https://github.com/homarr-labs/dashboard-icons (Apache-2.0; DASHBOARD-ICONS-LICENSE.txt). PNG artwork was resized and padded.

Papirus icons by Papirus Development Team and contributors: https://github.com/PapirusDevelopmentTeam/papirus-icon-theme (GPL-3.0; PAPIRUS-LICENSE.txt). SVG artwork was rasterized and padded.

Other images come from the app publishers, upstream project repositories or package-maintainer artwork; see sources.json for exact locations. Everything uses an official product screenshot. Some publishers supply horizontal wordmarks instead of square icons.

Developer refresh: install Pillow and resvg-py, then run python fetch_app_logos.py. Normal users do not need these tools.
