import multi_filter.admin_page as ap

groups = []
html = ap.render_admin_page(groups, {})
with open('dump.html', 'w', encoding='utf-8') as f:
    f.write(html)
