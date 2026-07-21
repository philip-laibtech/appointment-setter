def canonical_url(request):
    return {"canonical_url": request.build_absolute_uri(request.path)}
