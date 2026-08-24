from hose_source_surface_authority_qualification import CATALOG,SPA_SURFACES
def test_catalog_and_public_surface_roles_are_separate():
 assert CATALOG.startswith('https://staticfile.hsx.vn/') and len(SPA_SURFACES)==4
