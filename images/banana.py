import os
import sys
import time
from google import genai
from PIL import Image
from io import BytesIO
from sixel.converter import SixelConverter

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
model = "gemini-2.5-flash-image-preview"
#model = "gemini-2.0-flash-preview-image-generation"
config = genai.types.GenerateContentConfig(
    #temperature=1,
    #top_p=0.95,
    #top_k=40,
    #max_output_tokens=8192,
    response_modalities=["image", "text"],
    safety_settings=[
        genai.types.SafetySetting(
            category="HARM_CATEGORY_CIVIC_INTEGRITY",
            threshold="OFF",  # Off
        ),
    ],
    response_mime_type="text/plain",
)

def generate_content_retry(*args):
    """
    Generate content with retry logic for handling API errors
    
    Args:
        *args: Arguments to pass to generate_content
        
    Returns:
        Response object from the API
    """
    for i in range(5, 0, -1):
        try:
            response = client.models.generate_content(
                model=model,
                config=config,
                contents=args,
            )
            if response:
                if response.candidates:
                    if response.candidates[0].content:
                        return response
                    elif reason := response.candidates[0].finish_reason:
                        raise RuntimeError(reason)
                    else:
                        print(response.candidates)
                elif response.prompt_feedback:
                    print(response.prompt_feedback, file=sys.stderr)
            else:
                print(response, file=sys.stderr)
        except genai.errors.APIError as e:
            if hasattr(e, "code") and e.code in [429, 500, 502, 503]:
                print(e, file=sys.stderr)
            else:
                raise
        if i > 1:
            for j in range(15, -1, -1):
                print(f"\rRetrying... {j:2d}s", end="", file=sys.stderr, flush=True)
                if j:
                    time.sleep(1)
            print(file=sys.stderr)
    raise RuntimeError("Max retries exceeded.")

def display_image_sixel(image, width=640):
    """
    Resize image and display it in terminal using Sixel
    
    Args:
        image: PIL Image object
        width: Target width for terminal display (default: 256)
    """
    try:
        w = width
        h = int(w * image.height / image.width)
        resized_image = image.resize((w, h), resample=Image.LANCZOS)
        with BytesIO() as buf:
            resized_image.save(buf, format="PNG")
            SixelConverter(buf).write(sys.stdout)
    except Exception as e:
        print(f"Sixel display failed: {e}", file=sys.stderr)

def generate_and_save_image(contents, output_filename="output.png"):
    """
    Generate image using Gemini API with retry logic, save it, and display with Sixel
    
    Args:
        contents: List containing prompt and/or image for the model
        output_filename: Name of the output file to save the generated image
    
    Returns:
        bool: True if image was saved successfully, False otherwise
    """
    response = generate_content_retry(contents)
    
    for part in response.candidates[0].content.parts:
        if part.text is not None:
            print(part.text)
        elif part.inline_data is not None:
            image = Image.open(BytesIO(part.inline_data.data))
            image.save(output_filename)
            print(f"Image saved as {output_filename}")
            
            # Display image using Sixel
            display_image_sixel(image)
            
            return True
    
    return False
