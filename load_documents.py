#!/usr/bin/env python3
"""
Script to load all documents from resources/data into the database and embed them.
Run this once to populate your RAG system with documents.
"""

import sqlite3
import os
from pathlib import Path
import sys

# Add the app directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.rag_utils.rag_module import run_indexer

def load_all_documents():
    """Load all documents from resources/data into the database"""
    
    # Connect to database
    conn = sqlite3.connect("roles_docs.db")
    c = conn.cursor()
    
    # Clear existing documents (optional - remove if you want to keep existing)
    print("Clearing existing documents...")
    c.execute("DELETE FROM documents")
    
    # Base path to resources
    resources_path = Path("resources/data")
    
    # Document mapping: folder -> role
    folder_role_mapping = {
        "engineering": "Engineering",
        "finance": "Finance", 
        "hr": "HR",
        "marketing": "Marketing",
        "general": "General"
    }
    
    documents_added = 0
    
    for folder_name, role in folder_role_mapping.items():
        folder_path = resources_path / folder_name
        
        if not folder_path.exists():
            print(f"⚠️  Folder {folder_path} doesn't exist, skipping...")
            continue
            
        print(f"\n📁 Processing {role} documents from {folder_path}...")
        
        # Process all files in the folder
        for file_path in folder_path.glob("*"):
            if file_path.is_file() and file_path.suffix.lower() in ['.md', '.csv']:
                print(f"  📄 Adding: {file_path.name}")
                
                # Insert into database
                c.execute("""
                    INSERT INTO documents (filename, role, filepath, headers_str, embedded) 
                    VALUES (?, ?, ?, ?, ?)
                """, (file_path.name, role, str(file_path), "", 0))
                
                documents_added += 1
    
    # Commit changes
    conn.commit()
    conn.close()
    
    print(f"\n✅ Added {documents_added} documents to database")
    
    if documents_added > 0:
        print("🚀 Starting embedding process...")
        run_indexer()
        print("✅ All documents embedded successfully!")
    else:
        print("❌ No documents found to embed")

if __name__ == "__main__":
    print("🔄 Loading documents into RAG system...")
    load_all_documents()
    print("🎉 Document loading complete!")