import random

def apply_caption_style(caption, tone="random"):
    tone = tone.lower()
    if tone == "funny":
        return f"{caption} 😂👌"
    elif tone == "serious":
        return f"{caption}. Stay sharp. 🧠"
    elif tone == "witty":
        return f"{caption} 💡 You didn’t see that coming, did you?"
    elif tone == "confrontational":
        return f"{caption} Don’t like it? Clean it better. 🧼💥"
    elif tone == "random":
        return apply_caption_style(caption, tone=random.choice(["funny", "serious", "witty", "confrontational"]))
    else:
        return caption

