import xml.etree.ElementTree as ET
import re
import os

# The master SVG data provided in the prompt
RAW_SVG_DATA = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 768 256" width="768" height="256"> 
   <defs> 
     <!-- Lighting & Color Palettes --> 
     <linearGradient id="isoBaseTop" x1="0%" y1="0%" x2="100%" y2="100%"> 
       <stop offset="0%" stop-color="#475569"/><stop offset="100%" stop-color="#334155"/> 
     </linearGradient> 
     <linearGradient id="isoBaseRight" x1="0%" y1="0%" x2="0%" y2="100%"> 
       <stop offset="0%" stop-color="#1e293b"/><stop offset="100%" stop-color="#0f172a"/> 
     </linearGradient> 

     <!-- Skin & Hair --> 
     <linearGradient id="skin" x1="0%" y1="0%" x2="100%" y2="100%"> 
       <stop offset="0%" stop-color="#fed7aa"/><stop offset="100%" stop-color="#fdba74"/> 
     </linearGradient> 
     <linearGradient id="hairDark" x1="0%" y1="0%" x2="0%" y2="100%"> 
       <stop offset="0%" stop-color="#451a03"/><stop offset="100%" stop-color="#180e04"/> 
     </linearGradient> 
     <linearGradient id="hairGrey" x1="0%" y1="0%" x2="0%" y2="100%"> 
       <stop offset="0%" stop-color="#94a3b8"/><stop offset="100%" stop-color="#475569"/> 
     </linearGradient> 

     <!-- Tunic & Robe Colors -->
     <linearGradient id="paleWhite" x1="0%" y1="0%" x2="100%" y2="100%">
       <stop offset="0%" stop-color="#ffffff"/><stop offset="100%" stop-color="#cbd5e1"/>
     </linearGradient>
     <linearGradient id="crimsonRed" x1="0%" y1="0%" x2="100%" y2="100%">
       <stop offset="0%" stop-color="#f87171"/><stop offset="100%" stop-color="#991b1b"/>
     </linearGradient>
     <linearGradient id="gold" x1="0%" y1="0%" x2="100%" y2="100%"> 
       <stop offset="0%" stop-color="#fde047"/><stop offset="100%" stop-color="#ca8a04"/> 
     </linearGradient> 
      
     <linearGradient id="blueRobe" x1="0%" y1="0%" x2="100%" y2="100%"> 
       <stop offset="0%" stop-color="#38bdf8"/><stop offset="100%" stop-color="#0369a1"/> 
     </linearGradient> 
     <linearGradient id="greenRobe" x1="0%" y1="0%" x2="100%" y2="100%"> 
       <stop offset="0%" stop-color="#4ade80"/><stop offset="100%" stop-color="#15803d"/> 
     </linearGradient> 
     <linearGradient id="purpleRobe" x1="0%" y1="0%" x2="100%" y2="100%"> 
       <stop offset="0%" stop-color="#c084fc"/><stop offset="100%" stop-color="#6b21a8"/> 
     </linearGradient> 
     <linearGradient id="orangeRobe" x1="0%" y1="0%" x2="100%" y2="100%"> 
       <stop offset="0%" stop-color="#fb923c"/><stop offset="100%" stop-color="#c2410c"/> 
     </linearGradient> 
     <linearGradient id="tealRobe" x1="0%" y1="0%" x2="100%" y2="100%"> 
       <stop offset="0%" stop-color="#2dd4bf"/><stop offset="100%" stop-color="#0f766e"/> 
     </linearGradient> 
     <linearGradient id="brownRobe" x1="0%" y1="0%" x2="100%" y2="100%"> 
       <stop offset="0%" stop-color="#a16207"/><stop offset="100%" stop-color="#451a03"/> 
     </linearGradient> 

     <!-- Global Base & Shadow Template --> 
     <g id="iso-tile"> 
       <polygon points="32,63 49,54.5 32,46 15,54.5" fill="#000000" opacity="0.25"/> 
       <polygon points="17,55 32,62.5 32,60.5 17,53" fill="#334155"/> 
       <polygon points="32,62.5 47,55 47,53 32,60.5" fill="url(#isoBaseRight)"/> 
       <polygon points="17,53 32,60.5 47,53 32,45.5" fill="#64748b"/> 
       <polygon points="18,52.5 32,59.5 46,52.5 32,45.5" fill="url(#isoBaseTop)"/> 
       <polygon points="21,52 32,57.5 43,52 32,46.5" fill="#1e293b"/> 
     </g> 

     <g id="chibi-head"> 
       <!-- Base Head Cube/Sphere --> 
       <path d="M 32 30 L 38 33 L 32 36 L 26 33 Z" fill="url(#skin)"/> 
       <path d="M 26 33 L 32 36 L 32 41 L 26 38 Z" fill="url(#skin)"/> 
       <path d="M 32 36 L 38 33 L 38 38 L 32 41 Z" fill="url(#skin)"/> 
       <!-- Eyes --> 
       <circle cx="30.5" cy="37.8" r="0.8" fill="#0f172a"/> 
       <circle cx="33.5" cy="37.8" r="0.8" fill="#0f172a"/> 
       <circle cx="30.7" cy="37.6" r="0.3" fill="#ffffff"/> 
       <circle cx="33.7" cy="37.6" r="0.3" fill="#ffffff"/> 
     </g> 
   </defs> 

   <!-- ==================== ROW 1 (TOP) ==================== --> 

   <!-- 1. SIMON PETER (Keys) --> 
   <g transform="translate(64, 0)"> 
     <use href="#iso-tile"/> 
     <!-- Tunic & Robe --> 
     <path d="M 28 41.5 L 32 43.5 L 32 48 L 28 46 Z" fill="url(#blueRobe)"/> 
     <path d="M 32 43.5 L 36 41.5 L 36 46 L 32 48 Z" fill="url(#gold)"/> 
     <!-- Grey Hair & Beard --> 
     <path d="M 26 31 L 32 28 L 38 31 L 38 34 L 26 34 Z" fill="url(#hairGrey)"/> 
     <path d="M 26 38 L 32 43 L 38 38 L 38 41 L 32 44 L 26 41 Z" fill="url(#hairGrey)"/> 
     <use href="#chibi-head"/> 
     <!-- Keys of Heaven --> 
     <line x1="39" y1="45" x2="44" y2="30" stroke="url(#gold)" stroke-width="1.2"/> 
     <circle cx="44" cy="30" r="1.5" fill="none" stroke="url(#gold)" stroke-width="0.8"/> 
   </g> 

   <!-- 2. ANDREW (X-Cross) --> 
   <g transform="translate(192, 0)"> 
     <use href="#iso-tile"/> 
     <path d="M 28 41.5 L 32 43.5 L 32 48 L 28 46 Z" fill="url(#greenRobe)"/> 
     <path d="M 32 43.5 L 36 41.5 L 36 46 L 32 48 Z" fill="url(#paleWhite)"/>
     <!-- Long Grey Hair/Beard --> 
     <path d="M 25 32 L 32 27 L 39 32 L 38 42 L 26 42 Z" fill="url(#hairGrey)"/> 
     <use href="#chibi-head"/> 
     <!-- Saltire Cross on back --> 
     <line x1="18" y1="32" x2="28" y2="48" stroke="#78350f" stroke-width="1.5"/> 
     <line x1="18" y1="48" x2="28" y2="32" stroke="#78350f" stroke-width="1.5"/> 
   </g> 

   <!-- 3. JAMES THE GREATER (Staff & Pilgrim Shell) --> 
   <g transform="translate(320, 0)"> 
     <use href="#iso-tile"/> 
     <!-- Pilgrim Hat --> 
     <path d="M 24 31 Q 32 25 40 31" stroke="#451a03" stroke-width="2" fill="none"/> 
     <path d="M 28 41.5 L 32 43.5 L 32 48 L 28 46 Z" fill="url(#brownRobe)"/> 
     <path d="M 32 43.5 L 36 41.5 L 36 46 L 32 48 Z" fill="url(#greenRobe)"/> 
     <path d="M 26 33 L 32 29 L 38 33 L 38 37 L 26 37 Z" fill="url(#hairDark)"/> 
     <use href="#chibi-head"/> 
     <!-- Staff --> 
     <line x1="39" y1="48" x2="39" y2="25" stroke="#78350f" stroke-width="1.2"/> 
   </g> 

   <!-- 4. JOHN (Chalice & Eagle/Youthful) --> 
   <g transform="translate(448, 0)"> 
     <use href="#iso-tile"/> 
     <path d="M 28 41.5 L 32 43.5 L 32 48 L 28 46 Z" fill="url(#tealRobe)"/> 
     <path d="M 32 43.5 L 36 41.5 L 36 46 L 32 48 Z" fill="url(#crimsonRed)"/>
     <!-- Flowing Brown Hair (No Beard) --> 
     <path d="M 25 32 C 25 25, 39 25, 39 32 L 39 40 L 25 40 Z" fill="url(#hairDark)"/> 
     <use href="#chibi-head"/> 
     <!-- Golden Chalice --> 
     <polygon points="38,40 42,40 41,43 39,43" fill="url(#gold)"/> 
   </g> 

   <!-- 5. PHILIP (Cross Staff) --> 
   <g transform="translate(576, 0)"> 
     <use href="#iso-tile"/> 
     <path d="M 28 41.5 L 32 43.5 L 32 48 L 28 46 Z" fill="url(#orangeRobe)"/> 
     <path d="M 32 43.5 L 36 41.5 L 36 46 L 32 48 Z" fill="url(#blueRobe)"/> 
     <path d="M 26 32 L 32 28 L 38 32 L 38 36 L 26 36 Z" fill="url(#hairDark)"/> 
     <use href="#chibi-head"/> 
     <!-- Staff with Cross Top --> 
     <line x1="40" y1="48" x2="40" y2="26" stroke="#78350f" stroke-width="1.2"/> 
     <line x1="38" y1="29" x2="42" y2="29" stroke="#78350f" stroke-width="1.2"/> 
   </g> 

   <!-- ==================== ROW 2 (MIDDLE - CENTERPIECE) ==================== --> 

   <!-- 6. BARTHOLOMEW (Flaying Knife) --> 
   <g transform="translate(128, 80)"> 
     <use href="#iso-tile"/> 
     <path d="M 28 41.5 L 32 43.5 L 32 48 L 28 46 Z" fill="url(#purpleRobe)"/> 
     <path d="M 32 43.5 L 36 41.5 L 36 46 L 32 48 Z" fill="url(#paleWhite)"/>
     <path d="M 26 32 L 32 28 L 38 32 L 38 36 L 26 36 Z" fill="url(#hairDark)"/>
     <use href="#chibi-head"/>
     <!-- Knife -->
     <polygon points="39,40 41,36 40,43" fill="url(#paleWhite)"/> 
   </g> 

   <!-- PAUL (CENTER) -->
   <g transform="translate(320, 80)">
     <use href="#iso-tile"/>
     <!-- Traveler's Robe: brown tunic (tentmaker's cloth), purple trim (once a Pharisee) -->
     <path d="M 28 41.5 L 32 43.5 L 32 48 L 28 46 Z" fill="url(#brownRobe)"/>
     <path d="M 32 43.5 L 36 41.5 L 36 46 L 32 48 Z" fill="url(#purpleRobe)"/>
     <!-- Balding Hairline & Pointed Beard - no halo, unlike the master he preaches -->
     <path d="M 28 32 L 32 30.5 L 36 32 L 36 33.5 L 28 33.5 Z" fill="url(#hairDark)"/>
     <path d="M 27 38 L 32 44 L 37 38 L 36 41 L 32 45 L 28 41 Z" fill="url(#hairDark)"/>
     <use href="#chibi-head"/>
     <!-- A Letter/Scroll in hand (the epistle-writer) -->
     <rect x="37.5" y="39.5" width="4" height="2.4" rx="0.6" fill="url(#paleWhite)"/>
     <!-- Short Sword at his side (tradition holds he was beheaded for the faith) -->
     <line x1="23" y1="47" x2="23" y2="37.5" stroke="#94a3b8" stroke-width="1.3"/>
     <path d="M 21.5 37.5 L 24.5 37.5 L 23 35 Z" fill="#e2e8f0"/>
   </g>

   <!-- 7. THOMAS (Builder's Square / Spear) --> 
   <g transform="translate(512, 80)"> 
     <use href="#iso-tile"/> 
     <path d="M 28 41.5 L 32 43.5 L 32 48 L 28 46 Z" fill="url(#tealRobe)"/> 
     <path d="M 32 43.5 L 36 41.5 L 36 46 L 32 48 Z" fill="url(#orangeRobe)"/> 
     <path d="M 26 32 L 32 28 L 38 32 L 38 36 L 26 36 Z" fill="url(#hairDark)"/> 
     <use href="#chibi-head"/> 
     <!-- Builder's Square --> 
     <path d="M 38 42 L 38 34 L 43 34" stroke="url(#gold)" stroke-width="1.2" fill="none"/> 
   </g> 

   <!-- ==================== ROW 3 (BOTTOM) ==================== --> 

   <!-- 8. MATTHEW (Money Bag / Pen) --> 
   <g transform="translate(64, 160)"> 
     <use href="#iso-tile"/> 
     <path d="M 28 41.5 L 32 43.5 L 32 48 L 28 46 Z" fill="url(#greenRobe)"/> 
     <path d="M 32 43.5 L 36 41.5 L 36 46 L 32 48 Z" fill="url(#gold)"/> 
     <path d="M 26 32 L 32 28 L 38 32 L 38 36 L 26 36 Z" fill="url(#hairDark)"/> 
     <use href="#chibi-head"/> 
     <!-- Coin Purse --> 
     <circle cx="39" cy="42" r="2" fill="url(#brownRobe)"/> 
     <circle cx="39" cy="40" r="1" fill="url(#gold)"/> 
   </g> 

   <!-- 9. JAMES THE LESSER (Fuller's Club) --> 
   <g transform="translate(192, 160)"> 
     <use href="#iso-tile"/> 
     <path d="M 28 41.5 L 32 43.5 L 32 48 L 28 46 Z" fill="url(#paleWhite)"/>
     <path d="M 32 43.5 L 36 41.5 L 36 46 L 32 48 Z" fill="url(#purpleRobe)"/>
     <path d="M 26 32 L 32 28 L 38 32 L 38 36 L 26 36 Z" fill="url(#hairDark)"/>
     <use href="#chibi-head"/>
     <!-- Wooden Club --> 
     <line x1="39" y1="46" x2="42" y2="30" stroke="#451a03" stroke-width="2" stroke-linecap="round"/> 
   </g> 

   <!-- 10. JUDE THADDEUS (Axe / Club) --> 
   <g transform="translate(320, 160)"> 
     <use href="#iso-tile"/> 
     <path d="M 28 41.5 L 32 43.5 L 32 48 L 28 46 Z" fill="url(#orangeRobe)"/> 
     <path d="M 32 43.5 L 36 41.5 L 36 46 L 32 48 Z" fill="url(#tealRobe)"/> 
     <path d="M 26 32 L 32 28 L 38 32 L 38 36 L 26 36 Z" fill="url(#hairDark)"/> 
     <use href="#chibi-head"/> 
     <!-- Halberd/Axe -->
     <line x1="40" y1="48" x2="40" y2="28" stroke="#451a03" stroke-width="1.2"/>
     <path d="M 40 30 L 43 28 L 43 33 Z" fill="url(#paleWhite)"/> 
   </g> 

   <!-- 11. SIMON THE ZEALOT (Saw) --> 
   <g transform="translate(448, 160)"> 
     <use href="#iso-tile"/> 
     <path d="M 28 41.5 L 32 43.5 L 32 48 L 28 46 Z" fill="url(#purpleRobe)"/> 
     <path d="M 32 43.5 L 36 41.5 L 36 46 L 32 48 Z" fill="url(#greenRobe)"/> 
     <path d="M 26 31 L 32 27 L 38 31 L 38 35 L 26 35 Z" fill="url(#hairGrey)"/> 
     <use href="#chibi-head"/> 
     <!-- Hand Saw -->
     <line x1="39" y1="46" x2="39" y2="32" stroke="url(#paleWhite)" stroke-width="1.5"/> 
     <path d="M 39 32 L 41 34 L 39 36 L 41 38 L 39 40" stroke="#475569" stroke-width="0.8" fill="none"/> 
   </g> 

   <!-- 12. JUDAS ISCARIOT (30 Silver Coins Bag) --> 
   <g transform="translate(576, 160)"> 
     <use href="#iso-tile"/> 
     <!-- Darker/Muted Tunic --> 
     <path d="M 28 41.5 L 32 43.5 L 32 48 L 28 46 Z" fill="url(#brownRobe)"/> 
     <path d="M 32 43.5 L 36 41.5 L 36 46 L 32 48 Z" fill="#334155"/> 
     <path d="M 26 32 L 32 28 L 38 32 L 38 36 L 26 36 Z" fill="url(#hairDark)"/> 
     <use href="#chibi-head"/> 
     <!-- Money Pouch with Silver --> 
     <ellipse cx="23" cy="42" rx="2.5" ry="2" fill="#94a3b8"/> 
     <path d="M 23 40 L 22 38 L 24 38 Z" fill="url(#gold)"/> 
   </g> 
 </svg>"""

def slugify(text):
    """Converts text to a filename-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '_', text)
    text = re.sub(r'^-+|-+$', '', text)
    return text

def split_svg(xml_string, output_dir="individual_figures"):
    # Create output directory
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")

    # Fix clean up non-breaking spaces before parsing
    clean_xml = xml_string.replace('\xa0', ' ')
    
    try:
        root = ET.fromstring(clean_xml)
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}")
        return

    # SVG Namespace
    ns = {"svg": "http://www.w3.org/2000/svg"}
    ET.register_namespace("", ns["svg"])

    # 1. Extract <defs> string. We need to include this in every file.
    defs = root.find("svg:defs", ns)
    if defs is None:
        print("Error: Could not find <defs> in master SVG.")
        return
    defs_str = ET.tostring(defs, encoding="unicode")

    # 2. Find all figure groups <g> that have a transform attribute
    # In your code, these are the individual characters.
    figures = root.findall("svg:g[@transform]", ns)

    print(f"Found {len(figures)} figures. Starting split...")

    # We use regex to find comments because ElementTree standard parser ignores them.
    # We want to name files based on comments like "<!-- 1. SIMON PETER (Keys) -->"
    comment_pattern = re.compile(r'<!--\s*(.*?)\s*-->')
    
    # Find all comments in the raw string to match them up later
    all_comments = comment_pattern.findall(clean_xml)
    
    # Define a standard output size for individual assets
    # Based on iso-tile definitions, they fit within roughly 64x64, 
    # but halo/staff go higher. Let's use 64x80 adjusted.
    asset_width = 64
    asset_height = 80
    
    for i, fig in enumerate(figures):
        # Determine filename
        filename = f"figure_{i+1}.svg"
        
        # Try to find the associated comment name by looking at the XML 
        # structure just before this group. 
        # This is complex with ET, so we rely on the order of comments found via regex.
        # specifically looking for comments containing names.
        
        name_found = False
        # Look through found comments for names (ignoring structure comments like "skin & hair")
        potential_names = [c for c in all_comments if re.match(r'^\d+\.|PAUL', c)]
        
        if i < len(potential_names):
            raw_name = potential_names[i]
            # Clean up name, e.g., "1. SIMON PETER (Keys)" -> "simon_peter"
            clean_name = re.sub(r'^\d+\.\s*', '', raw_name) # remove "1. "
            clean_name = re.sub(r'\s*\(.*?\)', '', clean_name) # remove "(Keys)"
            filename = f"{slugify(clean_name)}.svg"
            print(f"Generating: {filename}")
        else:
             print(f"Generating: {filename} (Name not found in comments)")

        # Create new SVG root for the individual file
        # Setting viewBox to center the object defined around 32,40 (adjusted center)
        # Iso tile base is defined at x=32,y=46-63. Head around y=30.
        viewbox_str = f"0 0 {asset_width} {asset_height}"
        
        new_svg = ET.Element("svg", {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": viewbox_str,
            "width": str(asset_width),
            "height": str(asset_height)
        })

        # Add the defs
        new_svg.append(ET.fromstring(defs_str))

        # Import the figure group. ElementTree doesn't allow direct moving 
        # between trees easily, so we serialize and re-parse.
        fig_str = ET.tostring(fig, encoding="unicode")
        fig_entry = ET.fromstring(fig_str)

        # IMPORTANT: Remove the transform="translate(x, y)" 
        # so it renders at 0,0 in the new file.
        if 'transform' in fig_entry.attrib:
            del fig_entry.attrib['transform']
            
        # Add a wrapper group to center the figure within the new 64x80 canvas
        # The base is centered roughly at x=32. We translate -0 to center horizontally.
        # Vertically, the defined center is low, translate up slightly to fit canvas.
        wrapper = ET.SubElement(new_svg, "g", {"transform": "translate(0, 4)"})
        wrapper.append(fig_entry)

        # Write file
        output_path = os.path.join(output_dir, filename)
        
        # ElementTree.write usually works, but for specific formatting/headers 
        # tostring is safer on Windows/Unix
        with open(output_path, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(ET.tostring(new_svg, encoding="unicode"))

    print(f"\nSuccessfully generated {len(figures)} files in '{output_dir}' folder.")

if __name__ == "__main__":
    split_svg(RAW_SVG_DATA)