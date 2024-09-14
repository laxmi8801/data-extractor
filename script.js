import OpenAI from "openai";
import { MongoClient } from "mongodb";
import csvParser from 'csv-parser';
import fs from 'fs';
const openai = new OpenAI();
import Promise from "bluebird";

const labelReaderPrompt = `
You will be provided with a set of images corresponding to a single product. These images are found printed on the packaging of the product.
Your goal will be to extract information from these images to populate the schema provided. Here is some information you will routinely encounter. Ensure that you capture complete information, especially for nutritional information and ingredients.:
- Ingredients: List of ingredients in the item. They may have some percent listed in the bracket. They may also have some metadata or more classification
like Preservative (INS 211) where INS 211 forms the metadata. structure accordingly. If ingredients have subingredients like sugar: added sugar, trans sugar, treat them as different ingredients.
- Claims: Like a mango fruit juice says contains fruit
- Nutritional Information: This will have nutrients, serving size. It will have nutrients listed per serve, so we want that base value for reference.
It will also have RDA Values (Recommended Dietary Allowance) which we need to extract. 
- FSSAI License number: pack might have many license numbers, extract one of them and store other relevant information related to that number
- Name: Extract the name of product
- Brand/Manufactured By: Extract the parent company of this product
`

const quantitySchema =  {
  "quantity": {"type": "number"},
  "unit": {"type": "string"},
}

const nutritionalInfoSchema = {
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
        "additionalProperties": false
      }
    },
  },
  "required": ["name", "unit", "values"],
  "additionalProperties": false
}

async function extractInformation(imageLinks) {
  const imageMessage = imageLinks.map(il => {
    return {
      type: "image_url",
      image_url: {
        "url": il
      }
    }
  })
  const response = await openai.chat.completions.create({
    model: "gpt-4o-2024-08-06",
    messages: [
      {
        role: "user",
        content: [
          { type: "text", 
            text: labelReaderPrompt },
          ...imageMessage,
          {
            type: "image_url",
            image_url: {
              "url": "https://www.bigbasket.com/media/uploads/p/xl/1203607-5_3-frooti-drink-fresh-n-juicy-mango.jpg",
            },
          }
        ],
      },
    ],
    response_format:{
      "type": "json_schema",
      "json_schema": {
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
                              "metadata": {"type":"string"},
                          },
                          "required": ["name", "percent", "metadata"],
                          "additionalProperties": false
                      }
                  },
                  "servingSize": {
                    "type": "object",
                    "properties": quantitySchema,
                    "required": ["quantity", "unit"],
                    "additionalProperties": false
                  },
                  "servingsPerPack": {"type": "number"},
                  "nutritionalInformation": {
                    "type": "array",
                    "items": nutritionalInfoSchema,
                    "additionalProperties": true,
                  },
                  "fssaiLicenseNumbers": {"type": "array", "items": {"type": "number"}},
                  "claims": {"type": "array", "items": {"type": "string"}}
              },
              
              "required": ["productName", "brandName", "ingredients", "servingSize", "servingsPerPack", "nutritionalInformation", "fssaiLicenseNumbers", "claims"],
              "additionalProperties": false
          },
          "strict": true
      }
  }


  });
  const obj = response.choices[0]
  return obj
}

async function main() {
  const mongo = new MongoClient("mongodb://root:example@localhost:27017/");
  await mongo.connect();
  const db = mongo.db("consumeWise");
  const coll = db.collection("products");
  
  // read image links from csv 
  const csvPath = '/Users/seagull/Downloads/product2.csv';
  const results = []
  fs.createReadStream(csvPath)
  .pipe(csvParser({ headers: false }))
  .on('data', (data) => {
    const filteredData = []
    Object.values(data).forEach(v => {
      if(v){
        filteredData.push(v)
      }
    })
    results.push(filteredData)
  })
  .on('end', () => {
  // extract information
  Promise.map(results, async(imageLinks) => {
    const response = await extractInformation(imageLinks);
    if(!response.message || response.message.refusal) {
      console.error("Error in extracting information for product")
    }else {
      console.log('inserting document')
      await coll.insertOne(JSON.parse(response.message.content))
  
    }
  })
  });

}
main();