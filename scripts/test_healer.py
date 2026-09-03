#!/usr/bin/env python3
"""Test script to verify enemy healer functionality."""

from scripts.data_editor import load_characters_from_csv, load_skills_from_csv
from scripts.game_logic import Unit, choose_ai_action, SKILL_REGISTRY

# Load data
SKILL_REGISTRY.clear()
for skill_name, skill_data in load_skills_from_csv().items():
    SKILL_REGISTRY[skill_name] = skill_data

character_roster = load_characters_from_csv()
print("=== Characters Loaded ===")
for char in character_roster:
    print(f"{char['name']:15} Team: {char['team']:8} Skills: {char['skills']}")

# Create units
units = [Unit(char_data) for char_data in character_roster]

print("\n=== Unit Test ===")
for u in units:
    print(f"{u.name:15} Team: {u.team:8} HP: {u.hp}/{u.max_hp} MP: {u.mp}/{u.max_mp}")

# Test AI healing logic
print("\n=== Testing Enemy Healer AI ===")
meliadoul = next((u for u in units if u.name == "Meliadoul"), None)
if meliadoul:
    print(f"Found Meliadoul: {meliadoul.name}, Skills: {meliadoul.skills}")
    
    # Damage Knight B to test healing
    knight_b = next((u for u in units if u.name == "Knight B"), None)
    if knight_b:
        knight_b.hp = 50  # Damage the knight
        print(f"Damaged Knight B: HP now {knight_b.hp}/{knight_b.max_hp}")
        
        # Test AI action
        ai_action = choose_ai_action(meliadoul, units)
        print(f"Meliadoul AI action: {ai_action}")
        
        if ai_action["action"] == "skill" and ai_action["skill"] == "Chakra":
            print("✓ Healer correctly identified Knight B as target")
            print(f"  Will heal {ai_action['target'].name} (HP: {ai_action['target'].hp})")
        else:
            print("✗ Healer did not choose healing action")
else:
    print("✗ Meliadoul not found in character roster!")

print("\n=== Test Complete ===")
