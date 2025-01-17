import ifcopenshell
import ifcopenshell.util.element as ue
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, OWL, XSD
import uuid
import datetime
from typing import Dict, List, Optional

class IFCtoTTLConverter:
    def __init__(self):
        # Initialize an empty RDF graph to store our triples
        self.g = Graph()
        
        # Define standard ontology namespaces used in the conversion:
        # LFM: Legacy Facility Management ontology
        # BOT: Building Topology Ontology
        # OPM: Ontology for Property Management
        # SOSA: Sensor, Observation, Sample, and Actuator ontology
        # DOT: Damage Topology Ontology
        # TIME: Time Ontology
        # GEO: WGS84 Geo Positioning
        # IFC: Industry Foundation Classes
        self.LFM = Namespace("https://w3id.org/lfm#")
        self.BOT = Namespace("https://w3id.org/bot#")
        self.OPM = Namespace("http://www.w3.org/ns/opm#")
        self.SOSA = Namespace("http://www.w3.org/ns/sosa/")
        self.DOT = Namespace("https://w3id.org/dot#")
        self.TIME = Namespace("http://www.w3.org/2006/time#")
        self.GEO = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
        self.IFC = Namespace("http://standards.buildingsmart.org/IFC/DEV/IFC4/ADD2/OWL#")
        
        # Bind prefixes to namespaces for more readable output
        # This allows the output TTL file to use prefixed notation (e.g., bot:Building)
        # instead of full URIs
        self.g.bind("lfm", self.LFM)
        self.g.bind("bot", self.BOT)
        self.g.bind("opm", self.OPM)
        self.g.bind("sosa", self.SOSA)
        self.g.bind("dot", self.DOT)
        self.g.bind("time", self.TIME)
        self.g.bind("geo", self.GEO)
        self.g.bind("ifc", self.IFC)

    def generate_uri(self, prefix: str) -> URIRef:
        """
        Generate a unique URI for an entity using UUID
        Args:
            prefix: String to prefix the UUID (e.g., 'site', 'building')
        Returns:
            URIRef: A unique URI combining the prefix and a UUID
        """
        # Use the LFM namespace for our domain entities
        return URIRef(f"{self.LFM}{prefix}_{str(uuid.uuid4())}")

    def convert_spatial_structure(self, ifc_file) -> Dict[str, URIRef]:
        """
        Convert IFC spatial structure to BOT concepts
        Args:
            ifc_file: The loaded IFC file object
        Returns:
            Dictionary mapping IFC GlobalIds to their corresponding URIs
        """
        # Initialize dictionary to store mappings between IFC entities and their URIs
        uri_map = {}
        
        # Process sites - typically the highest level in the spatial hierarchy
        sites = ifc_file.by_type("IfcSite")
        for site in sites:
            site_uri = self.generate_uri("site")
            uri_map[site.GlobalId] = site_uri
            # Define the site as a BOT:Site
            self.g.add((site_uri, RDF.type, self.BOT.Site))
            
            # # Convert and add geolocation data if available
            # # IFC stores coordinates in degrees/minutes/seconds, convert to decimal
            # if site.RefLatitude and site.RefLongitude:
            #     lat = site.RefLatitude[0] + site.RefLatitude[1]/60 + site.RefLatitude[2]/3600
            #     long = site.RefLongitude[0] + site.RefLongitude[1]/60 + site.RefLongitude[2]/3600
            #     self.g.add((site_uri, self.GEO.lat, Literal(lat)))
            #     self.g.add((site_uri, self.GEO.long, Literal(long)))

        # Process buildings - contained within sites
        buildings = ifc_file.by_type("IfcBuilding")
        for building in buildings:
            building_uri = self.generate_uri("building")
            uri_map[building.GlobalId] = building_uri
            self.g.add((building_uri, RDF.type, self.BOT.Building))
            
            # Link to site
            if building.Decomposes:
                site_obj = building.Decomposes[0].RelatingObject
                if site_obj.GlobalId in uri_map:
                    self.g.add((uri_map[site_obj.GlobalId], self.BOT.hasBuilding, building_uri))

        # Process storeys - contained within buildings
        storeys = ifc_file.by_type("IfcBuildingStorey")
        for storey in storeys:
            storey_uri = self.generate_uri("storey")
            uri_map[storey.GlobalId] = storey_uri
            self.g.add((storey_uri, RDF.type, self.BOT.Storey))
            
            # Link to building
            if storey.Decomposes:
                building_obj = storey.Decomposes[0].RelatingObject
                if building_obj.GlobalId in uri_map:
                    self.g.add((uri_map[building_obj.GlobalId], self.BOT.hasStorey, storey_uri))

        # Process spaces - contained within storeys
        spaces = ifc_file.by_type("IfcSpace")
        for space in spaces:
            space_uri = self.generate_uri("space")
            uri_map[space.GlobalId] = space_uri
            self.g.add((space_uri, RDF.type, self.BOT.Zone))
            
            # Link to storey
            if space.Decomposes:
                storey_obj = space.Decomposes[0].RelatingObject
                if storey_obj.GlobalId in uri_map:
                    self.g.add((uri_map[storey_obj.GlobalId], self.BOT.hasZone, space_uri))

        return uri_map

    def convert_elements(self, ifc_file, uri_map: Dict[str, URIRef]):
        """
        Convert IFC building elements to BOT/LFM concepts
        Args:
            ifc_file: The loaded IFC file object
            uri_map: Dictionary mapping IFC GlobalIds to URIs
        """
        # Collect all concrete structural elements
        concrete_elements = ifc_file.by_type("IfcBeam") + ifc_file.by_type("IfcColumn") + \
                          ifc_file.by_type("IfcSlab") + ifc_file.by_type("IfcWall")
                          
        for element in concrete_elements:
            element_uri = self.generate_uri("element")
            uri_map[element.GlobalId] = element_uri
            
            # Add element type
            self.g.add((element_uri, RDF.type, self.BOT.Element))
            self.g.add((element_uri, RDF.type, self.LFM.ConcreteElement))
            
            # Add IFC representation
            ifc_class = element.is_a()
            self.g.add((element_uri, self.LFM.hasIfcRepresentation, 
                       URIRef(f"{self.IFC}{ifc_class}")))
            
            # Link to containing storey
            if hasattr(element, "ContainedInStructure"):
                for rel in element.ContainedInStructure:
                    if rel.RelatingStructure.GlobalId in uri_map:
                        self.g.add((uri_map[rel.RelatingStructure.GlobalId], 
                                  self.BOT.containsElement, element_uri))

            # Add material properties if available
            if element.HasAssociations:
                for association in element.HasAssociations:
                    if association.is_a('IfcRelAssociatesMaterial'):
                        material = association.RelatingMaterial
                        if material.is_a('IfcMaterial'):
                            # Create property state for material
                            prop_state = self.generate_uri("property_state")
                            self.g.add((prop_state, RDF.type, self.OPM.PropertyState))
                            self.g.add((prop_state, self.OPM.propertyName, 
                                      Literal("material")))
                            self.g.add((prop_state, self.OPM.value, 
                                      Literal(material.Name)))
                            self.g.add((element_uri, self.LFM.hasPropertyState, 
                                      prop_state))

    def convert_sensors(self, ifc_file, uri_map: Dict[str, URIRef]):
        """
        Convert IFC sensors to SOSA sensor concepts
        Args:
            ifc_file: The loaded IFC file object
            uri_map: Dictionary mapping IFC GlobalIds to URIs
        """
        sensors = ifc_file.by_type("IfcSensor")
        print(f"Found {len(sensors)} sensors")
        
        for sensor in sensors:
            sensor_uri = self.generate_uri("sensor")
            uri_map[sensor.GlobalId] = sensor_uri
            print(f"\nProcessing sensor: {sensor.GlobalId}")
            
            # Add sensor type
            self.g.add((sensor_uri, RDF.type, self.SOSA.Sensor))
            
            # Get all property sets for the sensor
            if hasattr(sensor, "IsDefinedBy"):
                for definition in sensor.IsDefinedBy:
                    if definition.is_a("IfcRelDefinesByProperties"):
                        property_set = definition.RelatingPropertyDefinition
                        if property_set.is_a('IfcPropertySet'):
                            print(f"Found property set: {property_set.Name}")
                            if property_set.Name == "Text":
                                for prop in property_set.HasProperties:
                                    print(f"- Property: {prop.Name}")
                                    if prop.Name == "SensorID" and hasattr(prop, "NominalValue"):
                                        print(f"Found SensorID: {prop.NominalValue.wrappedValue}")
                                        self.g.add((sensor_uri, RDFS.label, 
                                                  Literal(prop.NominalValue.wrappedValue)))
                                        
                                    if prop.Name == "SensorValueT" and hasattr(prop, "NominalValue"):
                                        print(f"Found SensorValueT: {prop.NominalValue.wrappedValue}")
                                        observation_uri = self.generate_uri("observation")
                                        self.g.add((observation_uri, RDF.type, self.SOSA.Observation))
                                        self.g.add((observation_uri, self.SOSA.madeBySensor, sensor_uri))
                                        self.g.add((observation_uri, self.SOSA.hasSimpleResult, 
                                                  Literal(prop.NominalValue.wrappedValue)))
                                        
                                        time_uri = self.generate_uri("instant")
                                        self.g.add((time_uri, RDF.type, self.TIME.Instant))
                                        self.g.add((time_uri, self.TIME.inXSDDateTimeStamp, 
                                                  Literal(datetime.datetime.now().isoformat(), 
                                                  datatype=XSD.dateTimeStamp)))
                                        self.g.add((observation_uri, self.SOSA.resultTime, time_uri))

    def convert_damage(self, ifc_file, uri_map: Dict[str, URIRef]):
        """
        Convert damage-related IFC properties to DOT damage concepts
        Args:
            ifc_file: The loaded IFC file object
            uri_map: Dictionary mapping IFC GlobalIds to URIs
        """
        damage_count = 0
        # Iterate through all elements to find damage-related properties
        for element in ifc_file.by_type("IfcElement"):
            if element.GlobalId in uri_map:
                element_uri = uri_map[element.GlobalId]
                print(f"\nChecking element: {element.GlobalId} ({element.is_a()})")
                
                # Check property sets directly through IsDefinedBy relationship
                if hasattr(element, "IsDefinedBy"):
                    for definition in element.IsDefinedBy:
                        if definition.is_a("IfcRelDefinesByProperties"):
                            property_set = definition.RelatingPropertyDefinition
                            if property_set.is_a('IfcPropertySet'):
                                print(f"Checking property set: {property_set.Name}")
                                
                                crack_id = None
                                host_guid = None
                                
                                # Look for Crack_ID and Host properties
                                for prop in property_set.HasProperties:
                                    if hasattr(prop, "NominalValue"):
                                        if prop.Name == "Crack_ID":
                                            crack_id = prop.NominalValue.wrappedValue
                                            print(f"Found Crack_ID: {crack_id}")
                                        elif prop.Name == "Host":
                                            host_guid = prop.NominalValue.wrappedValue
                                            print(f"Found Host: {host_guid}")
                                
                                # If we found a crack, create the damage entity
                                if crack_id:
                                    damage_count += 1
                                    damage_uri = self.generate_uri("damage")
                                    self.g.add((damage_uri, RDF.type, self.DOT.Damage))
                                    self.g.add((damage_uri, RDFS.label, Literal(crack_id)))
                                    
                                    # Link to host element if found in uri_map
                                    if host_guid and host_guid in uri_map:
                                        self.g.add((uri_map[host_guid], self.LFM.hasDamageAssessment, 
                                                  damage_uri))
                                    
                                    # Add other damage properties
                                    for prop in property_set.HasProperties:
                                        if (hasattr(prop, "NominalValue") and 
                                            prop.Name not in ["Crack_ID", "Host"]):
                                            prop_state = self.generate_uri("property_state")
                                            self.g.add((prop_state, RDF.type, self.OPM.PropertyState))
                                            self.g.add((prop_state, self.OPM.propertyName, 
                                                      Literal(prop.Name)))
                                            self.g.add((prop_state, self.OPM.value, 
                                                      Literal(prop.NominalValue.wrappedValue)))
                                            self.g.add((damage_uri, self.LFM.hasPropertyState, 
                                                      prop_state))
        
        print(f"\nTotal damage instances found: {damage_count}")

    def convert(self, ifc_file_path: str, output_path: str):
        """
        Main conversion method that orchestrates the entire IFC to TTL conversion process
        Args:
            ifc_file_path: Path to the input IFC file
            output_path: Path where the output TTL file should be saved
        """
        # Load the IFC file using ifcopenshell
        ifc_file = ifcopenshell.open(ifc_file_path)
        
        # Convert the spatial structure first (site, building, storey)
        # This creates the basic containment hierarchy
        uri_map = self.convert_spatial_structure(ifc_file)
        
        # Convert building elements (beams, columns, etc.)
        self.convert_elements(ifc_file, uri_map)
        
        # Convert sensor elements and their relationships
        self.convert_sensors(ifc_file, uri_map)
        
        # Convert damage information from property sets
        self.convert_damage(ifc_file, uri_map)
        
        # Save the resulting graph to a Turtle (TTL) file
        self.g.serialize(destination=output_path, format='turtle')

def main():
    # Example usage
    converter = IFCtoTTLConverter()
    converter.convert("W20.ifc", "W20.ttl")

if __name__ == "__main__":
    main()