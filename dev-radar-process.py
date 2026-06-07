#!/usr/bin/env python3
import json
import re
import os
from datetime import datetime

def extract_domain(url):
    """Extract domain from URL"""
    if not url:
        return ""
    match = re.search(r'https?://([^/]+)/?', url)
    return match.group(1) if match else ""

def check_duplicate(candidate, existing_entries):
    """Check if candidate already exists in entries based on domain, url, or name"""
    candidate_domain = ""
    for link_url in candidate.get('links', {}).values():
        candidate_domain = extract_domain(link_url)
        if candidate_domain:
            break
    
    # Check by domain
    if candidate_domain:
        for entry in existing_entries:
            for link_url in entry.get('links', {}).values():
                entry_domain = extract_domain(link_url)
                if entry_domain and entry_domain == candidate_domain:
                    return True, f"重复域名: {candidate_domain}"
    
    # Check by name
    candidate_name = candidate.get('name', '').lower()
    for entry in existing_entries:
        entry_name = entry.get('name', '').lower()
        if candidate_name and entry_name and candidate_name == entry_name:
            return True, f"重复名称: {candidate_name}"
    
    # Check by URL
    for link_url in candidate.get('links', {}).values():
        for entry in existing_entries:
            for existing_url in entry.get('links', {}).values():
                if link_url and existing_url and link_url == existing_url:
                    return True, f"重复URL: {link_url}"
    
    return False, ""

def is_android_related(candidate):
    """Check if candidate is Android-related based on category and tags"""
    category = candidate.get('category', '').lower()
    tags = [tag.lower() for tag in candidate.get('tags', [])]
    
    android_keywords = ['android', 'perfetto', 'tracing', 'render', 'power', 'startup', 'memory']
    
    if category in ['android', 'android-official', 'android-blog', 'android-community', 'tools']:
        return True
    
    for tag in tags:
        if any(keyword in tag for keyword in android_keywords):
            return True
    
    return False

def generate_funnel_entry(candidate):
    """Generate FUNNEL-style entry for AIW daily-info"""
    category = candidate.get('category', '')
    tags = candidate.get('tags', [])
    desc = candidate.get('desc', '')
    author = candidate.get('author', candidate.get('name', ''))
    
    # Find main link
    main_link = None
    for link_type, link_url in candidate.get('links', {}).items():
        if link_type in ['blog', 'github', 'website', 'x']:
            main_link = link_url
            break
    
    if not main_link:
        main_link = list(candidate.get('links', {}).values())[0] if candidate.get('links') else ""
    
    return {
        'title': f"📱 Android技术发现: {candidate.get('name', '')}",
        'content': f"🎯 领域: {category}\n🏷️ 标签: {', '.join(tags)}\n📝 内容: {desc}\n👤 作者: {author}\n🔗 链接: {main_link}",
        'timestamp': datetime.now().isoformat(),
        'source': 'dev-radar-auto'
    }

def main():
    # Read files
    with open('/tmp/Rss-IT/data/candidates.json', 'r', encoding='utf-8') as f:
        candidates_data = json.load(f)
    
    with open('/tmp/Rss-IT/data/entries.json', 'r', encoding='utf-8') as f:
        entries_data = json.load(f)
    
    candidates = candidates_data.get('candidates', [])
    existing_entries = entries_data.get('entries', [])
    
    today = "2026-06-07"
    accepted_entries = []
    skipped_candidates = []
    processed_count = 0
    
    for candidate in candidates:
        processed_count += 1
        
        # Check for duplicates
        is_duplicate, duplicate_reason = check_duplicate(candidate, existing_entries)
        
        # Make decision based on quality and other factors
        quality = candidate.get('quality', 0)
        
        # Skip if duplicate
        if is_duplicate:
            skipped_candidates.append({
                'name': candidate['name'],
                'reason': '重复'
            })
            continue
        
        # Apply quality rules
        if quality >= 4:
            # Default accept, unless duplicate already handled
            decision = 'accept'
        elif quality == 3:
            # Need to check for unique value
            decision = 'accept'  # For now, accept all quality 3 unless duplicate
        else:
            decision = 'skip'
        
        if decision == 'accept':
            # Create new entry
            new_entry = {
                'id': candidate['id'],
                'name': candidate['name'],
                'category': candidate['category'],
                'author': candidate.get('author', ''),
                'desc': candidate['desc'],
                'links': candidate['links'],
                'tags': candidate['tags'],
                'quality': candidate['quality'],
                'added_date': today
            }
            
            accepted_entries.append(new_entry)
        else:
            skipped_candidates.append({
                'name': candidate['name'],
                'reason': '质量低'
            })
    
    # Update entries.json
    entries_data['entries'].extend(accepted_entries)
    entries_data['updated'] = today
    
    # Write updated entries.json
    with open('/tmp/Rss-IT/data/entries.json', 'w', encoding='utf-8') as f:
        json.dump(entries_data, f, ensure_ascii=False, indent=2)
    
    # Generate AIW entries for Android-related content
    aiw_entries = []
    for entry in accepted_entries:
        if is_android_related(entry):
            aiw_entry = generate_funnel_entry(entry)
            aiw_entries.append(aiw_entry)
    
    # Write AIW entries if any
    if aiw_entries:
        os.makedirs('/tmp/Rss-IT/aiw-daily-info', exist_ok=True)
        aiw_file = f'/tmp/Rss-IT/aiw-daily-info/dev-radar-{today}.json'
        with open(aiw_file, 'w', encoding='utf-8') as f:
            json.dump(aiw_entries, f, ensure_ascii=False, indent=2)
    
    # Create empty candidates.json (all processed)
    candidates_data['candidates'] = []
    candidates_data['last_updated'] = today
    candidates_data['processed_count'] = processed_count
    candidates_data['processed_date'] = today
    
    with open('/tmp/Rss-IT/data/candidates.json', 'w', encoding='utf-8') as f:
        json.dump(candidates_data, f, ensure_ascii=False, indent=2)
    
    # Generate report
    report = {
        'date': today,
        'accepted_count': len(accepted_entries),
        'skipped_count': len(skipped_candidates),
        'total_candidates': processed_count,
        'accepted_names': [entry['name'] for entry in accepted_entries],
        'skipped_reasons': skipped_candidates
    }
    
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()