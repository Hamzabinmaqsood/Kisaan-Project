from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Districts
from .serializers import DistrictsSerializer

# GET all + POST
@api_view(['GET', 'POST'])
def district_list_create(request):
    if request.method == 'GET':
        districts = Districts.objects.all()
        serializer = DistrictsSerializer(districts, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        serializer = DistrictsSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# GET one + PUT + DELETE
@api_view(['GET', 'PUT', 'DELETE'])
def district_detail(request, pk):
    try:
        district = Districts.objects.get(pk=pk)
    except Districts.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = DistrictsSerializer(district)
        return Response(serializer.data)

    elif request.method == 'PUT':
        serializer = DistrictsSerializer(district, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        district.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)