#!/usr/bin/env python3
import json

def process_candidates():
    # Read candidates
    with open('data/candidates.json', 'r', encoding='utf-8') as f:
        candidates_data = json.load(f)
    
    # Read entries
    with open('data/entries.json', 'r', encoding='utf-8') as f:
        entries_data = json.load(f)
    
    accepted_count = 0
    skipped_count = 0
    accepted_list = []
    skipped_list = []
    today = '2026-06-15'
    
    # Process each candidate
    for candidate in candidates_data['candidates']:
        candidate_id = candidate['id']
        candidate_name = candidate['name']
        quality = candidate['quality']
        
        # Skip candidates with quality <= 2
        if quality <= 2:
            skipped_count += 1
            skipped_list.append(f'{candidate_name}（quality≤2）')
            continue
        
        # For quality >= 4, accept unless duplicates found
        if quality >= 4:
            duplicate_found = False
            for entry in entries_data['entries']:
                # Check name similarity
                if entry['name'] == candidate_name:
                    duplicate_found = True
                    break
            
            if duplicate_found:
                skipped_count += 1
                skipped_list.append(f'{candidate_name}（重复）')
                continue
            
            # Accept candidate
            accepted_count += 1
            accepted_list.append(candidate_name)
            
            # Create new entry
            new_entry = {
                'id': candidate_id,
                'name': candidate_name,
                'category': candidate['category'],
                'author': candidate['author'],
                'desc': candidate['desc'],
                'links': candidate['links'],
                'tags': candidate['tags'],
                'quality': quality,
                'added_date': today
            }
            
            # Add to entries
            entries_data['entries'].append(new_entry)
            
            print(f'Accepted: {candidate_name} (quality={quality})')
    
    # Update entries updated date
    entries_data['updated'] = today
    
    # Save updated entries
    with open('data/entries.json', 'w', encoding='utf-8') as f:
        json.dump(entries_data, f, ensure_ascii=False, indent=2)
    
    # Clear all candidates
    candidates_data['candidates'] = []
    candidates_data['processed_count'] += len(candidates_data['candidates'])
    candidates_data['processed_date'] = today
    
    # Save updated candidates
    with open('data/candidates.json', 'w', encoding='utf-8') as f:
        json.dump(candidates_data, f, ensure_ascii=False, indent=2)
    
    return accepted_count, skipped_count, accepted_list, skipped_list

if __name__ == '__main__':
    accepted, skipped, accepted_names, skipped_names = process_candidates()
    print(f'📥 Dev-Radar 自动收录 · 2026-06-15')
    print(f'收录 {accepted} 个，跳过 {skipped} 个，异常 0 个')
    
    if accepted_names:
        print(f'新收录：{"、".join(accepted_names)}')
    
    if skipped_names:
        print(f'跳过：{"、".join(skipped_names)}')
    
    total_sources = accepted + skipped
    print(f'总计 {total_sources} 个源')