with open('dashboard/static/styles.css', 'r') as f:
    content = f.read()

# 1. Remove margin-left: 8px from status-pill (was added in media query, not needed globally)
content = content.replace(
    "  white-space: nowrap;\n  flex-shrink: 0;\n  margin-left: 8px;\n}",
    "  white-space: nowrap;\n  flex-shrink: 0;\n}"
)

# 2. Update the @media (max-width: 480px) block for better mobile layout
old_media = """@media (max-width: 480px) {
  .dir-detail-row {
    flex-wrap: wrap;
  }
}"""

new_media = """@media (max-width: 480px) {
  .dir-detail-row {
    flex-wrap: wrap;
  }

  .dir-detail-link {
    flex: 1;
    min-width: 0;
  }

  .dir-name {
    font-size: 18px;
  }

  .dir-subtitle {
    font-size: 11px;
  }

  .search-term-tag {
    font-size: 10px;
    padding: 1px 8px;
  }
}"""

if old_media in content:
    content = content.replace(old_media, new_media)
    updated = True
else:
    updated = False

with open('dashboard/static/styles.css', 'w') as f:
    f.write(content)

print(f"Media query updated: {updated}")
print(f"flex-shrink: 0 present: {'flex-shrink: 0;' in content}")
print(f"search-term-tag font-size 10px in media: {'font-size: 10px' in content}")
print("Done")
