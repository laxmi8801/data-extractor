import os
import openai
import pymongo
import json
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from PIL import Image
import io
import base64
from bson import ObjectId
# Load environment variables from .env file
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Set OpenAI API key
openai.api_key = api_key

# MongoDB connection
client = pymongo.MongoClient("mongodb+srv://consumewise_db:p123%40@cluster0.sodps.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client.consumeWise
collection = db.products

# Define the prompt that will be passed to the OpenAI API
label_reader_prompt = """
You will be provided with a set of images corresponding to a single product. These images are found printed on the packaging of the product.
Your goal will be to extract information from these images to populate the schema provided. Here is some information you will routinely encounter. Ensure that you capture complete information, especially for nutritional information and ingredients:
- Ingredients: List of ingredients in the item. They may have some percent listed in brackets. They may also have metadata or classification like Preservative (INS 211) where INS 211 forms the metadata. Structure accordingly. If ingredients have subingredients like sugar: added sugar, trans sugar, treat them as different ingredients.
- Claims: Like a mango fruit juice says contains fruit.
- Nutritional Information: This will have nutrients, serving size, and nutrients listed per serving. Extract the base value for reference.
- FSSAI License number: Extract the license number. There might be many, so store relevant ones.
- Name: Extract the name of the product.
- Brand/Manufactured By: Extract the parent company of this product.
- Serving size: This might be explicitly stated or inferred from the nutrients per serving.
"""

# Function to extract information from image URLs
def extract_information(image_links):
    print("in extract_information")
    image_message = [{"type": "image_url", "image_url": {"url": il}} for il in image_links]
    
    # Send the request to OpenAI API with the images and prompt
    response = openai.ChatCompletion.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": label_reader_prompt},
                    *image_message,
                ],
            },
        ],
        response_format={"type": "json_schema", "json_schema": {
            "name": "label_reader",
            "schema": {
                "type": "object",
                "properties": {
                    "productName": {"type": "string"},
                    "brandName": {"type": "string"},
                    "ingredients": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "percent": {"type": "string"},
                                "metadata": {"type": "string"},
                            },
                            "required": ["name", "percent", "metadata"],
                            "additionalProperties": False
                        }
                    },
                    "servingSize": {
                        "type": "object",
                        "properties": {
                            "quantity": {"type": "number"},
                            "unit": {"type": "string"},
                        },
                        "required": ["quantity", "unit"],
                        "additionalProperties": False
                    },
                    "packagingSize": {
                        "type": "object",
                        "properties": {
                            "quantity": {"type": "number"},
                            "unit": {"type": "string"},
                        },
                        "required": ["quantity", "unit"],
                        "additionalProperties": False
                    },
                    "servingsPerPack": {"type": "number"},
                    "nutritionalInformation": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "unit": {"type": "string"},
                                "values": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "base": {"type": "string"},
                                            "value": {"type": "number"},
                                        },
                                        "required": ["base", "value"],
                                        "additionalProperties": False
                                    }
                                },
                            },
                            "required": ["name", "unit", "values"],
                            "additionalProperties": False
                        },
                        "additionalProperties": True,
                    },
                    "fssaiLicenseNumbers": {"type": "array", "items": {"type": "number"}},
                    "claims": {"type": "array", "items": {"type": "string"}},
                    "shelfLife": {"type": "string"},
                },
                "required": [
                    "productName", "brandName", "ingredients", "servingSize",
                    "packagingSize", "servingsPerPack", "nutritionalInformation",
                    "fssaiLicenseNumbers", "claims", "shelfLife"
                ],
                "additionalProperties": False
            },
            "strict": True
        }}
    )
    
    # Extract and return the relevant response
    obj = response['choices'][0]
    return obj

# Route to accept image URLs and return extracted JSON data
@app.route("/extract", methods=["POST"])
def extract_data():
    try:
        # Get image URLs from the request JSON body
        data = request.json
        image_links = data.get('image_links')
        
        if not image_links:
            return jsonify({"error": "No image URLs provided"}), 400
        
        # Call the extraction function
        extracted_data = extract_information(image_links)
        print("extracted data called")
        
        if 'message' in extracted_data and not extracted_data['message'].get('refusal'):
            ans = json.loads(extracted_data['message']['content'])
            # Store in MongoDB
            print("if condition")
            collection.insert_one(ans)
            return jsonify("data added"), 200
        else:
            return jsonify({"error": "Failed to extract information"}), 500
        
    except Exception as error:
        return jsonify({"error": str(error)}), 500
# Route to get product information by product name or _id
@app.route("/product", methods=["GET"])
def get_product():
    try:
        # Get product name or ID from query parameters
        product_id = request.args.get('id')
        product_name = request.args.get('name')

        if product_id:
            # Find product by ID
            product = collection.find_one({"_id": ObjectId(product_id)})
            print(f"Searching by ID: {product_id}")
        elif product_name:
            # Find product by name
            product = collection.find_one({"productName": product_name})
            print(f"Searching by Name: {product_name}")
        else:
            return jsonify({"error": "Please provide a valid product name or id"}), 400

        if not product:
            print("Product not found.")
            return jsonify({"error": "Product not found"}), 404
        if product:
            product['_id'] = str(product['_id'])
            print(f"Found product: {json.dumps(product, indent=4)}")
            return jsonify(product), 200

        # Convert ObjectId to string for JSON response
        
        
    except Exception as error:
        return jsonify({"error": str(error)}), 500
# Main function to run Flask app
if __name__ == "__main__":
    app.run(debug=True)
