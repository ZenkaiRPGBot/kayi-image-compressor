"""
app/bot/messages/texts.py

All user-facing message text constants for Kayi Image Compressor.
Uses Telegram HTML parse mode throughout.
"""

WELCOME_CAPTION = """\
<b>Kayi Image Compressor</b>

Compress smarter. Share faster.

Send me any image — JPEG, PNG, or WebP — and I'll reduce its file size while preserving as much quality as possible.

<b>What I can do:</b>
✦ Auto compress with one tap
✦ Hit a specific target file size
✦ Choose quality presets
✦ Strip metadata for privacy
✦ Convert between formats

Need help? Use /help for instructions and feature guides.\
"""

WELCOME_TEXT = """\
<b>Kayi Image Compressor</b>

Compress smarter. Share faster.

Send me any image — JPEG, PNG, or WebP — and I'll reduce its file size while preserving as much quality as possible.

Need help? Use /help for instructions and feature guides.\
"""

FSUB_REQUIRED = """\
<b>Join Required</b>

To use Kayi Image Compressor, please join our official channel first.

This helps us keep the service running.\
"""

FSUB_NOT_JOINED = """\
<b>Not Joined Yet</b>

It looks like you haven't joined yet. Please join the channel and try again.\
"""

HELP_MAIN = """\
<b>Kayi Image Compressor — Help</b>

<b>Getting Started</b>
Just send any image. I'll detect the format and show you compression options immediately.

<b>Supported Formats</b>
✦ Input: JPEG, PNG, WebP
✦ Output: JPEG, PNG, WebP (choose during compression)

<b>Compression Modes</b>

<b>Auto Optimize</b>
One tap — I pick the best quality-to-size balance automatically.

<b>Quality Presets</b>
✦ <b>Best Quality</b> — High quality, moderate reduction
✦ <b>Balanced</b> — Good quality, significant reduction
✦ <b>Smallest File</b> — Maximum reduction, reduced quality
✦ <b>Lossless</b> — No quality loss (PNG/WebP only)

<b>Target Size</b>
Specify an exact target in KB. I'll binary-search the optimal quality to get as close as possible.

<b>Limits</b>
✦ Max upload: 8 MB per image
✦ Max resolution: 12 megapixels
✦ Daily limit: 20 compressions per user

<b>Privacy</b>
EXIF metadata (location, device info) is stripped by default.
Use /privacy to learn more.\
"""

HELP_PRIVACY = """\
<b>Privacy & Data Handling</b>

<b>Your images are processed securely:</b>

✦ Files are downloaded temporarily for processing only.
✦ EXIF metadata (location, device, timestamps) is stripped from all outputs by default.
✦ Processed files are deleted immediately after delivery.
✦ No images are stored on disk beyond the active session.
✦ Sessions expire after 10 minutes of inactivity.
✦ No user data is sold or shared with third parties.

<b>Limitations</b>
Session data (your current image) is stored in memory only and is not persisted across bot restarts.\
"""

IMAGE_RECEIVED = """\
<b>Image Received</b>

<b>Format:</b> {fmt}
<b>Size:</b> {size}
<b>Dimensions:</b> {dimensions}

How would you like to compress it?\
"""

PROCESSING = "⏳ Compressing your image…"

QUEUE_FULL = """\
<b>Queue Full</b>

The compression queue is currently at capacity. Please try again in a moment.\
"""

RATE_LIMITED = """\
<b>Slow Down</b>

{reason}\
"""

RESULT_SUCCESS = """\
<b>Compressed Successfully</b>

<b>Original:</b> {original_size}
<b>Compressed:</b> {output_size}
<b>Saved:</b> {saved} ({reduction}%)
<b>Format:</b> {fmt}
<b>Dimensions:</b> {dimensions}\
"""

RESULT_GREW = """\
<b>Compression Result</b>

The compressed file is slightly larger than the original ({output_size} vs {original_size}).
This can happen with already-optimized images or lossless formats.

The original quality has been preserved.\
"""

TARGET_MET = "\n\n✦ <b>Target met:</b> {target_kb} KB"
TARGET_NOT_MET = "\n\n⚠️ <b>Target not met.</b> Closest achievable: {actual_kb} KB\n{reason}"

COMPRESSION_FAILED = """\
<b>Compression Failed</b>

Something went wrong while processing your image.

{error}

Please try again or send a different image.\
"""

TIMEOUT_ERROR = """\
<b>Processing Timeout</b>

Your image took too long to process and the job was cancelled.

This can happen with very large or complex images. Please try a smaller image or a different preset.\
"""

SESSION_EXPIRED = """\
<b>Session Expired</b>

Your compression session has expired. Please send your image again.\
"""

TARGET_PROMPT = """\
<b>Enter Target Size</b>

Send the target file size in KB (e.g. <code>200</code> for 200 KB).

Current image: {size}\
"""

TARGET_INVALID = """\
<b>Invalid Size</b>

Please enter a number in KB (e.g. <code>200</code> for 200 KB).\
"""

CANCEL_OK = "✦ Cancelled. Send another image any time."

ANOTHER_IMAGE = "Send me another image to compress."
