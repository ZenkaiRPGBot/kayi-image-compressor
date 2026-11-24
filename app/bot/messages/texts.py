"""
app/bot/messages/texts.py

All user-facing message text constants for Kayi Image Compressor.
Matches the official visual and typographic standards of the Kayi Bots ecosystem:
  - Clean Telegram HTML formatting
  - Generous whitespace
  - ✦ bullet points
  - No decorative borders or excessive emojis
"""

WELCOME_CAPTION = (
    "<b>Welcome to Kayi Image Compressor</b>\n\n"
    "Compress smarter. Share faster.\n\n"
    "Reduce image file sizes for portals, forms, and sharing while preserving quality.\n\n"
    "✦ Smart target-size compression\n"
    "✦ Quality and specialized presets\n"
    "✦ Form upload and custom dimensions\n"
    "✦ Privacy-first metadata stripping\n\n"
    "Need help? Use /help for instructions and feature guides.\n\n"
    "<i>Send an image or file to begin.</i>"
)

WELCOME_TEXT = WELCOME_CAPTION

HELP_TEXT = (
    "<b>Kayi Image Compressor — Help</b>\n\n"
    "Compress and optimize images with precision.\n\n"
    "<b>Getting Started</b>\n\n"
    "✦ Send any photo or image file (JPEG, PNG, WebP) directly to the bot.\n\n"
    "✦ Choose a compression mode or target file size.\n\n"
    "✦ Receive your compressed image with full optimization statistics.\n\n"
    "<b>Compression Modes</b>\n\n"
    "✦ <b>Auto Optimize</b> — Recommended one-tap balance of quality and file size.\n\n"
    "✦ <b>Target Size</b> — Select 20 KB, 50 KB, 100 KB, 200 KB, 500 KB, 1 MB, or any custom size. Quality is calibrated using binary search.\n\n"
    "✦ <b>Form Upload Mode</b> — Perfect for government, job, or university portals. Set exact or max dimensions, target file size, and fit preferences without distortion.\n\n"
    "✦ <b>Specialized Presets</b> — Optimized modes for Photos, Screenshots/Text, Signatures, Form/ID Photos, and Transparent images.\n\n"
    "✦ <b>Lossless Mode</b> — Optimizes file structure without altering a single decoded pixel.\n\n"
    "<b>Privacy & Limits</b>\n\n"
    "✦ EXIF metadata (camera, location, device details) is stripped by default.\n\n"
    "✦ Max upload: 8 MB. Max resolution: 12 megapixels.\n\n"
    "✦ All temporary processing files are purged immediately after delivery.\n\n"
    "<b>Need Assistance?</b>\n\n"
    "Contact @qouba if you encounter an issue."
)

PRIVACY_TEXT = (
    "<b>Privacy & Data Handling</b>\n\n"
    "✦ <b>Ephemeral Processing</b> — Images are downloaded into temporary memory strictly during processing.\n\n"
    "✦ <b>Metadata Removal</b> — EXIF headers (location coordinates, device info, timestamps) are stripped from compressed outputs by default.\n\n"
    "✦ <b>Immediate Cleanup</b> — Processed files and sessions are purged immediately after delivery or upon session expiration (10 minutes).\n\n"
    "✦ <b>No Tracking or Storage</b> — We do not permanently store images or sell user data.\n\n"
    "<i>Notice: Temporary sessions reset whenever server updates occur.</i>"
)

IMAGE_CARD_TEMPLATE = (
    "<b>Image Received</b>\n\n"
    "• <b>Format:</b> <code>{fmt}</code>\n"
    "• <b>Size:</b> <code>{size}</code>\n"
    "• <b>Dimensions:</b> <code>{dimensions}</code>\n\n"
    "{suggestion}\n"
    "<i>Select a compression option below:</i>"
)

PROCESSING_TEXT = "⏳ <i>Compressing image...</i>"

RESULT_CAPTION_TEMPLATE = (
    "<b>Compressed Successfully ✅</b>\n\n"
    "• <b>Original:</b> <code>{original_size}</code>\n"
    "• <b>Compressed:</b> <code>{output_size}</code>\n"
    "• <b>Saved:</b> <code>{saved} ({reduction}%)</code>\n"
    "• <b>Format:</b> <code>{fmt}</code>\n"
    "• <b>Dimensions:</b> <code>{dimensions}</code>\n"
    "{target_line}"
    "{background_line}"
    "{suggestion_line}"
)

RESULT_ALREADY_OPTIMAL = (
    "<b>Already Optimal ✅</b>\n\n"
    "• <b>Original:</b> <code>{original_size}</code>\n"
    "• <b>Current Size:</b> <code>{output_size}</code>\n"
    "• <b>Format:</b> <code>{fmt}</code>\n\n"
    "✦ The image is already optimally compressed without pixel loss.\n"
    "✦ Further reduction requires lossy compression or resizing."
)

FORM_VALIDATION_FAILED = (
    "⚠️ <b>Form Requirement Alert</b>\n\n"
    "The output was generated, but could not satisfy all strict constraints:\n\n"
    "{errors}\n\n"
    "<i>Try adjusting dimension constraints or enabling proportional padding.</i>"
)

QUEUE_BUSY_TEXT = (
    "⚠️ <b>Compression Queue Busy</b>\n\n"
    "The processing worker is currently handling maximum jobs. "
    "Please try again in a few moments."
)

SESSION_EXPIRED_TEXT = (
    "⚠️ <b>Session Expired</b>\n\n"
    "Your temporary compression session has timed out (10 min limit). "
    "Please send your image again to continue."
)
